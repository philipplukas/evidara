"""Run a query through sparse retrieval **and** ADR-0054 D4's gate, against a live index.

This is the command behind Step 5 of `docs/runbooks/sparse-embedding-backfill.md`.
It replaces a hand-rolled `curl` with something that issues the query the way the
gate's calibration was measured, so a later run is comparable to the committed
fixture rather than to a differently-shaped query.

It writes nothing. Its whole job is to answer, for one query: does the corpus
have an answer, or does the platform refuse — and on what number.

Re-measuring the calibration
----------------------------
    uv run --extra embeddings python -m document_intelligence.jobs.sparse_gate_probe \\
      --opensearch-url "http://$CLUSTER_IP:9200" \\
      --queries-file document-intelligence/tests/fixtures/sparse_gate_calibration.json \\
      --json > /tmp/recalibration.json

The fixture's `queries[]` entries carry `label` (`IN`/`OUT`), so a labelled run
also prints the confusion matrix the floor is accountable to. It does **not**
exit non-zero on a leak: a floor that lets a hard query through is a measurement
to act on, not a broken process, and turning it into a red exit is how a floor
gets tuned to whatever the last sample was.
"""

from __future__ import annotations

import argparse
import json
import logging
import sys
import urllib.error
import urllib.request
from pathlib import Path
from typing import Any

from document_intelligence.embeddings.gating import (
    Candidate,
    GateConfig,
    GateDecision,
    gate,
    query_weight_mass,
)
from document_intelligence.embeddings.sparse import SparseEncoder

logger = logging.getLogger(__name__)

DEFAULT_INDEX = "documents-write"
SPARSE_FIELD = "content_sparse"

#: How many query features are sent as `rank_feature` clauses. The gate's
#: denominator is the mass of *this* truncated vector, not of the full one —
#: otherwise the ratio describes a query that was never issued.
DEFAULT_QUERY_FEATURES = 512


class SearchClient:
    """The two reads this probe makes. Not a general client."""

    def __init__(self, base_url: str, *, timeout: float = 60.0) -> None:
        self.base_url = base_url.rstrip("/")
        self.timeout = timeout

    def _post(self, path: str, body: dict[str, Any]) -> dict[str, Any]:
        request = urllib.request.Request(
            f"{self.base_url}{path}",
            data=json.dumps(body).encode("utf-8"),
            headers={"Content-Type": "application/json"},
            method="POST",
        )
        with urllib.request.urlopen(request, timeout=self.timeout) as response:
            return json.loads(response.read().decode("utf-8"))

    def count(self, index: str) -> int:
        response = self._post(f"/{index}/_search", {"size": 0, "query": {"match_all": {}}})
        return int(response.get("hits", {}).get("total", {}).get("value", 0))

    def sparse_search(self, index: str, vector: dict[str, float], *, size: int) -> list[Candidate]:
        should = [
            {"rank_feature": {"field": f"{SPARSE_FIELD}.{feature}", "boost": weight, "linear": {}}}
            for feature, weight in vector.items()
        ]
        if not should:
            return []
        response = self._post(
            f"/{index}/_search", {"size": size, "_source": False, "query": {"bool": {"should": should}}}
        )
        return [Candidate(hit["_id"], float(hit["_score"])) for hit in response.get("hits", {}).get("hits", [])]

    def bm25_hits(self, index: str, query: str) -> int:
        """The contrast #891 rests on: what the lexical retriever did with the same query."""
        response = self._post(
            f"/{index}/_search",
            {"size": 0, "query": {"multi_match": {"query": query, "fields": ["title^4", "content"]}}},
        )
        return int(response.get("hits", {}).get("total", {}).get("value", 0))


def probe_query(
    client: SearchClient,
    encoder: SparseEncoder,
    query: str,
    *,
    index: str,
    corpus_size: int,
    max_features: int,
    config: GateConfig,
) -> tuple[GateDecision, dict[str, Any]]:
    full = encoder.encode_query(query)
    # Truncate first, then take the mass of what was actually sent.
    sent = dict(sorted(full.items(), key=lambda item: -item[1])[:max_features])
    mass = query_weight_mass(sent)
    candidates = client.sparse_search(index, sent, size=max(config.top_n, config.margin_top_k))
    decision = gate(candidates, mass=mass, corpus_size=corpus_size, config=config)
    context = {
        "query": query,
        "query_features": len(sent),
        "query_features_before_truncation": len(full),
        "bm25_hits": client.bm25_hits(index, query),
    }
    return decision, context


def load_queries(args: argparse.Namespace) -> list[tuple[str | None, str]]:
    """(label, query) pairs. Label is None when the caller gave no ground truth."""
    pairs: list[tuple[str | None, str]] = [(None, q) for q in (args.query or [])]
    if args.queries_file:
        payload = json.loads(Path(args.queries_file).read_text(encoding="utf-8"))
        rows = payload["queries"] if isinstance(payload, dict) else payload
        pairs.extend((row.get("label"), row["query"]) for row in rows)
    return pairs


def build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(description="Probe sparse retrieval through ADR-0054 D4's abstention gate.")
    parser.add_argument("--opensearch-url", default="http://opensearch-cluster-master:9200")
    parser.add_argument("--index", default=DEFAULT_INDEX)
    parser.add_argument("--model", default="BAAI/bge-m3")
    parser.add_argument("--device", default=None, help="cuda:0, cpu, ... (default: auto)")
    parser.add_argument("--query", action="append", help="A query to probe. Repeatable.")
    parser.add_argument(
        "--queries-file",
        help="JSON with a `queries` list of {label, query} — e.g. the committed calibration fixture.",
    )
    parser.add_argument("--max-features", type=int, default=DEFAULT_QUERY_FEATURES)
    parser.add_argument(
        "--coverage-floor",
        type=float,
        default=GateConfig().coverage_floor,
        help="Override D4's absolute floor, to see what a different knob would decide.",
    )
    parser.add_argument("--enable-margin", action="store_true", help="Also apply D4's margin-collapse rule.")
    parser.add_argument("--json", action="store_true", help="Emit machine-readable decisions on stdout.")
    return parser


def main(argv: list[str] | None = None) -> int:
    logging.basicConfig(level=logging.INFO, format="%(levelname)s %(message)s")
    args = build_parser().parse_args(argv)

    pairs = load_queries(args)
    if not pairs:
        logger.error("no queries: pass --query or --queries-file")
        return 2

    config = GateConfig(coverage_floor=args.coverage_floor, margin_enabled=args.enable_margin)
    client = SearchClient(args.opensearch_url)
    encoder = SparseEncoder(args.model, device=args.device)

    try:
        corpus_size = client.count(args.index)
        records: list[dict[str, Any]] = []
        for label, query in pairs:
            decision, context = probe_query(
                client,
                encoder,
                query,
                index=args.index,
                corpus_size=corpus_size,
                max_features=args.max_features,
                config=config,
            )
            records.append({"label": label, **context, "decision": decision.as_dict()})
    except (urllib.error.URLError, urllib.error.HTTPError, KeyError) as exc:
        # A probe that could not run is not a probe that found nothing.
        logger.error("probe failed: %s", exc)
        return 1

    if args.json:
        print(
            json.dumps(
                {"index": args.index, "corpus_size": corpus_size, "records": records}, indent=2, ensure_ascii=False
            )
        )
    else:
        for record in records:
            decision = record["decision"]
            verdict = "ADMIT " if decision["admitted"] else f"REFUSE({decision['refusal_reason']})"
            coverage = decision["coverage"]
            print(
                f"{verdict:24} coverage={coverage if coverage is None else round(coverage, 5)!s:<9} "
                f"top={decision['top_score']} mass={decision['query_weight_mass']} "
                f"sparse_hits={decision['candidates_in']} bm25_hits={record['bm25_hits']}  {record['query']!r}"
            )

    labelled = [r for r in records if r["label"] in {"IN", "OUT"}]
    if labelled:
        withheld = [r["query"] for r in labelled if r["label"] == "IN" and not r["decision"]["admitted"]]
        leaked = [r["query"] for r in labelled if r["label"] == "OUT" and r["decision"]["admitted"]]
        print(
            json.dumps(
                {
                    "config_version": config.version,
                    "coverage_floor": config.coverage_floor,
                    "labelled_queries": len(labelled),
                    "in_corpus_withheld": withheld,
                    "out_of_corpus_admitted": leaked,
                },
                indent=2,
                ensure_ascii=False,
            ),
            file=sys.stderr,
        )
    return 0


if __name__ == "__main__":  # pragma: no cover
    sys.exit(main())
