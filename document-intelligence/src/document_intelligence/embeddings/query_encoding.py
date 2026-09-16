"""Query-side sparse encoding, as a service the search path can call (ADR-0054).

The document side of the learned-sparse representation already ships: 882 of the 889
production documents carry `content_sparse`, written by
`document_intelligence.jobs.embedding_backfill`. Nothing can *query* it, because the
query has to be encoded by the same model and no serving component runs one.

WHY THE MODEL AND NOT JUST THE TOKENIZER
----------------------------------------
This looks like a place to save a 2.3GB download. It is not, and the measurement is
worth keeping because the shortcut is so tempting.

BGE-M3's query features are a strict SUBSET of its tokenizer's ids — measured
2026-09-16 on *"Darf ich meinen Hund in Zürich ohne Leine laufen lassen"*: 10 model
features, 12 tokenizer ids, overlap 10, model-only 0. So a tokenizer-only encoder
would produce the same feature SPACE and needs no torch.

What it cannot produce is the weights, and the weights are the point:

    Zürich  0.2612      laufen  0.1547      lassen  0.0667
    Hund    0.2349      ohne    0.1267      meinen  0.0496

Uniform weighting makes `meinen` worth as much as `Hund`. Corpus-IDF weighting is
worse than uniform here: measured over the 903-document corpus, `ich` appears in 5
documents and `meinen` in 3, against `Hund` in 13 — colloquial first-person German is
RARER in statutes than the legal subject, so IDF actively rewards it. That is #973
rebuilt in the sparse arm, and #973 needed a hand-written stopword filter to undo.

So the query path needs the model. It is a cold path by design (see below), so it may
be slow and CPU-bound; it may not be wrong.

WHY A COLD PATH MAKES THIS AFFORDABLE
-------------------------------------
Sparse retrieval is not intended to re-rank every query. Measured over 27 realistic
lay-vocabulary queries, BM25 returns results for 23 and zero for 4 — so an encoder
invoked only when the lexical arm finds nothing runs on ~15% of traffic. At that rate
a 100-300ms CPU encode is acceptable, and the 21.5GB CUDA image
(`Dockerfile.embeddings`) is not needed at all.

This module does not decide when to call it. It answers honestly when asked, and
reports enough for a caller to apply ADR-0054 D4's gate: the truncated vector AND the
weight mass of exactly that vector.
"""

from __future__ import annotations

import logging
from typing import NamedTuple

from document_intelligence.embeddings.gating import query_weight_mass
from document_intelligence.embeddings.sparse import SparseEncoder, SparseVector

logger = logging.getLogger(__name__)

#: Features sent to OpenSearch as `rank_feature` clauses. Matches
#: `jobs.sparse_gate_probe.DEFAULT_QUERY_FEATURES`, deliberately: the D4 floor was
#: calibrated against a 512-feature query, and a ratio computed over a differently
#: sized vector is not comparable to it.
DEFAULT_MAX_FEATURES = 512

#: Upper bound a caller may ask for. BGE-M3 emits a long tail of near-zero weights;
#: past a few hundred features the clauses cost query time and contribute no ranking.
MAX_FEATURES_CEILING = 2048


class QueryEncoderUnavailable(RuntimeError):
    """The encoder cannot run here — a deployment fact, not a query problem.

    Carries a stable `reason` so a caller can answer 503 with a named cause instead of
    letting an ImportError surface as a 500. "The model is not installed in this image"
    and "this query is unanswerable" must not look the same to the search path — that
    is #958's *absent vs broken* at the service boundary.
    """

    def __init__(self, reason: str, detail: str) -> None:
        super().__init__(detail)
        self.reason = reason
        self.detail = detail


class QuerySparseResult(NamedTuple):
    """An encoded query, and everything needed to gate the search it will drive."""

    features: SparseVector
    #: Features the model produced BEFORE truncation. When this exceeds
    #: `len(features)` the caller is searching with a reduced query and can say so.
    features_before_truncation: int
    #: Weight mass of `features` as returned — the truncated vector, never the full
    #: one. ADR-0054 D4's coverage ratio divides by this; dividing by the untruncated
    #: mass would describe a query that was never issued.
    weight_mass: float
    truncated: bool
    model: str


_encoder: SparseEncoder | None = None


def _get_encoder(model: str) -> SparseEncoder:
    """Load once per process. The first call pays the model load; the rest do not."""
    global _encoder
    if _encoder is None or _encoder.model_name != model:
        _encoder = SparseEncoder(model)
    return _encoder


def encode_query(
    text: str,
    *,
    max_features: int = DEFAULT_MAX_FEATURES,
    model: str = "BAAI/bge-m3",
) -> QuerySparseResult:
    """Encode `text` into the same feature space `content_sparse` is written in.

    Raises `ValueError` for an empty query and `QueryEncoderUnavailable` when the
    `embeddings` extra is absent from this image.
    """
    query = text.strip()
    if not query:
        raise ValueError("query must not be empty")
    if max_features < 1:
        raise ValueError("max_features must be >= 1")
    max_features = min(max_features, MAX_FEATURES_CEILING)

    encoder = _get_encoder(model)
    try:
        full = encoder.encode_query(query)
    except RuntimeError as exc:
        # SparseEncoder._load() raises this when FlagEmbedding is missing. Translate it
        # rather than letting the search path read a 500 as "retrieval is broken".
        if "embeddings` extra" in str(exc) or "FlagEmbedding" in str(exc):
            raise QueryEncoderUnavailable(
                "embeddings_extra_not_installed",
                "This document-service image does not carry the sparse encoder. "
                "Install the `embeddings` extra, or route query encoding to a build that has it.",
            ) from exc
        raise

    ranked = sorted(full.items(), key=lambda item: -item[1])
    kept = dict(ranked[:max_features])
    return QuerySparseResult(
        features=kept,
        features_before_truncation=len(full),
        weight_mass=query_weight_mass(kept),
        truncated=len(full) > len(kept),
        model=model,
    )
