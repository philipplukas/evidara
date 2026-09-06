"""BGE-M3 learned-sparse encoding, and the pure functions around it.

The model half of this module is a thin wrapper. Everything that decides what
lands in the index — chunking, pooling, feature-name sanitisation — is a pure
function tested without the model, because a test that needs a 2.3GB download to
run is a test that does not run.

WHY TOKEN IDS AND NOT TOKEN STRINGS AS FEATURE NAMES
----------------------------------------------------
`rank_features` keys are arbitrary strings, which is exactly the problem: BGE-M3's
lexical weights are keyed by token id, and the decoded strings for a multilingual
vocabulary include `.`, empty strings, and SentencePiece continuation markers.
A `.` in a feature name is read as object nesting by OpenSearch, so a decoded
vocabulary silently produces a *different* field structure than intended for some
tokens and not others — the class of defect that presents as "search works, but
not for these documents".

Keying on the token id (`t<id>`) removes the question. Both sides encode through
the same tokenizer, so query and document agree by construction. The cost is
honest and worth stating: a `rank_features` map keyed by id is **not** readable
by a human inspecting a document, which gives up part of the interpretability
advantage sparse retrieval otherwise has over a dense vector. `decode_features()`
exists so an operator can get the readable form back when they need it.
"""

from __future__ import annotations

import logging
from collections.abc import Iterable, Iterator, Sequence
from typing import Any, Protocol

logger = logging.getLogger(__name__)

#: A sparse vector as it is written to OpenSearch: feature name -> positive weight.
SparseVector = dict[str, float]

#: BGE-M3's context window. Chunking happens below this, not at it: the tokenizer
#: is not a character counter, and a chunk that overflows is silently truncated by
#: the model rather than rejected — losing the tail of a long article with no error.
MODEL_MAX_TOKENS = 8192

#: Characters per chunk. Deliberately conservative against MODEL_MAX_TOKENS:
#: German legal text tokenises worse than English (compounds split into several
#: pieces), so a ratio near 1 char/token is the safe assumption, not 4.
DEFAULT_CHUNK_CHARS = 6000

#: Overlap between chunks, so a provision spanning a boundary is fully present in
#: at least one chunk rather than bisected in both.
DEFAULT_CHUNK_OVERLAP = 400

#: Weights below this contribute nothing to ranking but do cost index size. BGE-M3
#: emits a long tail of near-zero lexical weights.
DEFAULT_MIN_WEIGHT = 0.01


class _LexicalEncoder(Protocol):
    """The slice of BGEM3FlagModel this module uses, so tests can substitute it."""

    def encode(self, sentences: Sequence[str], **kwargs: Any) -> dict[str, Any]: ...


def chunk_text(
    text: str,
    *,
    chunk_chars: int = DEFAULT_CHUNK_CHARS,
    overlap: int = DEFAULT_CHUNK_OVERLAP,
) -> list[str]:
    """Split `text` into overlapping windows.

    This is a *window*, not a semantic split: the sections index is where
    structural granularity belongs (ADR-0054 D7). Windowing exists so that a
    213,735-character constitution produces a representation at all, rather than
    being silently truncated to its first 8192 tokens — which is what passing it
    whole to the model would do.
    """
    if chunk_chars <= 0:
        raise ValueError("chunk_chars must be positive")
    if overlap < 0 or overlap >= chunk_chars:
        raise ValueError("overlap must be non-negative and smaller than chunk_chars")

    stripped = text.strip()
    if not stripped:
        return []
    if len(stripped) <= chunk_chars:
        return [stripped]

    step = chunk_chars - overlap
    chunks = [stripped[start : start + chunk_chars] for start in range(0, len(stripped), step)]
    # The final window can be a short tail already wholly contained in its
    # predecessor; encoding it again would double-count its tokens under max
    # pooling for no gain.
    if len(chunks) > 1 and len(chunks[-1]) <= overlap:
        chunks.pop()
    return chunks


def pool_sparse_chunks(chunks: Iterable[SparseVector]) -> SparseVector:
    """Combine per-chunk sparse vectors by **max**, not by sum or mean.

    Max is the choice that keeps a long document comparable to a short one. Sum
    would make weight a proxy for length, so the constitution would outrank every
    ordinance on every term it happens to contain; mean would dilute a term that
    is decisive in one article of forty. Max asks "how strongly does this
    document express this term anywhere in itself", which is the question a
    document-level retrieval score is trying to answer.
    """
    pooled: SparseVector = {}
    for chunk in chunks:
        for feature, weight in chunk.items():
            current = pooled.get(feature)
            if current is None or weight > current:
                pooled[feature] = weight
    return pooled


def sanitize_features(
    features: dict[str, float] | dict[int, float],
    *,
    min_weight: float = DEFAULT_MIN_WEIGHT,
) -> SparseVector:
    """Normalise raw lexical weights into something `rank_features` accepts.

    `rank_features` rejects a document outright if any value is zero or negative
    — the whole bulk item fails, not the field — so filtering here is what stops
    one degenerate token from dropping a document out of the index entirely.
    """
    cleaned: SparseVector = {}
    for raw_key, raw_weight in features.items():
        try:
            weight = float(raw_weight)
        except (TypeError, ValueError):
            continue
        if weight <= 0.0 or weight < min_weight:
            continue
        key = raw_key if isinstance(raw_key, str) else f"t{raw_key}"
        if not key.startswith("t"):
            key = f"t{key}"
        # Defence in depth: even the id-keyed form must never carry a character
        # OpenSearch reads structurally.
        if "." in key or not key[1:].isdigit():
            continue
        cleaned[key] = weight
    return cleaned


class SparseEncoder:
    """BGE-M3 lexical weights, on GPU when one is available.

    The model is loaded lazily so that importing this module — which the CLI and
    the tests both do — costs nothing until an encode is actually requested.
    """

    def __init__(
        self,
        model_name: str = "BAAI/bge-m3",
        *,
        device: str | None = None,
        use_fp16: bool = True,
        min_weight: float = DEFAULT_MIN_WEIGHT,
        chunk_chars: int = DEFAULT_CHUNK_CHARS,
        chunk_overlap: int = DEFAULT_CHUNK_OVERLAP,
        _model: _LexicalEncoder | None = None,
    ) -> None:
        self.model_name = model_name
        self.device = device
        self.use_fp16 = use_fp16
        self.min_weight = min_weight
        self.chunk_chars = chunk_chars
        self.chunk_overlap = chunk_overlap
        self._model = _model

    @property
    def model(self) -> _LexicalEncoder:
        if self._model is None:
            self._model = self._load()
        return self._model

    def _load(self) -> _LexicalEncoder:
        try:
            from FlagEmbedding import BGEM3FlagModel
        except ImportError as exc:  # pragma: no cover - exercised by the extra's absence
            raise RuntimeError(
                "The `embeddings` extra is not installed. Install with: uv sync --extra embeddings"
            ) from exc

        resolved = self.device or self._default_device()
        logger.info("loading sparse encoder", extra={"model": self.model_name, "device": resolved})
        # fp16 is a real speedup on a modern GPU and meaningless on CPU, where it
        # is also numerically worse — so it follows the device rather than the flag.
        return BGEM3FlagModel(
            self.model_name,
            use_fp16=self.use_fp16 and resolved.startswith("cuda"),
            devices=resolved,
        )

    @staticmethod
    def _default_device() -> str:
        try:
            import torch
        except ImportError:  # pragma: no cover
            return "cpu"
        return "cuda:0" if torch.cuda.is_available() else "cpu"

    def encode_documents(self, texts: Sequence[str], *, batch_size: int = 4) -> list[SparseVector]:
        """Encode whole documents, chunking and pooling each.

        Chunks from every document are encoded in one flat batch so the GPU is
        not left idle between documents of wildly different length — which, in a
        corpus mixing a 213k-character constitution with a two-page ordinance, is
        the difference between saturating the card and not.
        """
        per_document: list[list[str]] = [
            chunk_text(text, chunk_chars=self.chunk_chars, overlap=self.chunk_overlap) for text in texts
        ]
        flat = [chunk for chunks in per_document for chunk in chunks]
        if not flat:
            return [{} for _ in texts]

        encoded = self._encode_chunks(flat, batch_size=batch_size)

        results: list[SparseVector] = []
        cursor = 0
        for chunks in per_document:
            take = encoded[cursor : cursor + len(chunks)]
            cursor += len(chunks)
            results.append(pool_sparse_chunks(take))
        return results

    def _encode_chunks(self, chunks: Sequence[str], *, batch_size: int) -> list[SparseVector]:
        output = self.model.encode(
            list(chunks),
            batch_size=batch_size,
            max_length=MODEL_MAX_TOKENS,
            return_dense=False,
            return_sparse=True,
            return_colbert_vecs=False,
        )
        raw = output["lexical_weights"]
        return [sanitize_features(item, min_weight=self.min_weight) for item in raw]

    def encode_query(self, text: str) -> SparseVector:
        """Encode a query with the same tokenizer the documents used."""
        return self._encode_chunks([text], batch_size=1)[0]

    def decode_features(self, vector: SparseVector) -> dict[str, float]:
        """Map `t<id>` feature names back to readable tokens, for operators.

        Not used on the write path — see the module docstring on why the index
        stores ids.
        """
        try:
            from transformers import AutoTokenizer
        except ImportError as exc:  # pragma: no cover
            raise RuntimeError("transformers is required to decode features") from exc
        tokenizer = AutoTokenizer.from_pretrained(self.model_name)
        readable: dict[str, float] = {}
        for key, weight in vector.items():
            token = tokenizer.decode([int(key[1:])]).strip()
            if token:
                readable[token] = weight
        return readable


def iter_batches(items: Sequence[Any], size: int) -> Iterator[list[Any]]:
    """Yield `items` in lists of at most `size`."""
    if size <= 0:
        raise ValueError("size must be positive")
    for start in range(0, len(items), size):
        yield list(items[start : start + size])
