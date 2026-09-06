"""Backfill `content_sparse` onto documents already in the search index (ADR-0054).

WHAT THIS IS, AND WHAT IT DELIBERATELY IS NOT
---------------------------------------------
This job adds **one derived field** to documents that are already projected. It
does not build a projection, does not create an index, and does not decide what a
document is. That distinction is the whole reason it is allowed to write to
OpenSearch at all:

- Index *creation* is first-writer-wins, so a second creation path does not merely
  disagree with `documents-index.mapping.ts` — it silently wins over it (#675,
  #713). This job creates nothing; it refuses to run against an index whose
  mapping lacks `content_sparse`, rather than adding the field itself.
- The projection *shape* is owned by `ProjectionsService` in legal-search, and
  `delta_projection_backfill` goes to some length to keep it there. This job does
  not reconstruct any part of that shape.

The long-term home for this field is the `document.processed` event, so live
traffic carries it and the BFF maps it like every other field. That is a
contract change (`contracts/events/document-processed.schema.json` plus the
manifest version bump), and it is deliberately not made here: the point of this
job is to prove the representation is servable before a contract is committed to
it. See ADR-0054 D8.

WHY IT READS `content` FROM THE INDEX RATHER THAN FROM DELTA
------------------------------------------------------------
ADR-0005 makes canonical Delta the truth and the index a serving layer, and
`delta_projection_backfill` reads Delta for exactly that reason. This job reads
the indexed `content` instead, because the thing being embedded must be the thing
being searched: if the projection truncated, normalised or dropped text on its way
into the index, an embedding computed from Delta would describe a document the
index does not contain. Deriving the sparse field from the indexed text keeps the
representation and the retrieval target identical by construction.

The consequence is stated rather than hidden: a document whose `content` is
missing from the index gets no sparse vector, and this job reports it as skipped
instead of silently writing an empty map. An empty `rank_features` map is not
neutral — it is a document that can never match a sparse query, which is
indistinguishable at query time from a document that legitimately does not match.
"""

from __future__ import annotations

import argparse
import json
import logging
import sys
import time
import urllib.error
import urllib.request
from dataclasses import dataclass, field
from typing import Any

from document_intelligence.embeddings.sparse import SparseEncoder

logger = logging.getLogger(__name__)

DEFAULT_INDEX = "documents-write"
SPARSE_FIELD = "content_sparse"


@dataclass
class BackfillReport:
    """What a run did, in terms an operator can act on."""

    scanned: int = 0
    embedded: int = 0
    updated: int = 0
    skipped_no_content: list[str] = field(default_factory=list)
    failed: list[str] = field(default_factory=list)
    elapsed_seconds: float = 0.0

    def as_dict(self) -> dict[str, Any]:
        return {
            "scanned": self.scanned,
            "embedded": self.embedded,
            "updated": self.updated,
            "skipped_no_content": self.skipped_no_content,
            "failed": self.failed,
            "elapsed_seconds": round(self.elapsed_seconds, 2),
        }


class OpenSearchClient:
    """The three calls this job makes. Not a general client."""

    def __init__(self, base_url: str, *, timeout: float = 60.0) -> None:
        self.base_url = base_url.rstrip("/")
        self.timeout = timeout

    def _request(self, method: str, path: str, body: Any = None, *, ndjson: bool = False) -> Any:
        url = f"{self.base_url}{path}"
        data = None
        headers = {}
        if body is not None:
            if ndjson:
                data = body.encode("utf-8")
                headers["Content-Type"] = "application/x-ndjson"
            else:
                data = json.dumps(body).encode("utf-8")
                headers["Content-Type"] = "application/json"
        request = urllib.request.Request(url, data=data, headers=headers, method=method)
        with urllib.request.urlopen(request, timeout=self.timeout) as response:
            return json.loads(response.read().decode("utf-8"))

    def mapping_has_sparse_field(self, index: str) -> bool:
        """True when every physical index behind `index` maps SPARSE_FIELD.

        Checked per physical index, not once: against an alias, a half-migrated
        set is exactly the state worth catching, and `documents-read` really is
        an alias here.
        """
        mapping = self._request("GET", f"/{index}/_mapping")
        if not mapping:
            return False
        return all(SPARSE_FIELD in body.get("mappings", {}).get("properties", {}) for body in mapping.values())

    def scroll_documents(self, index: str, *, page_size: int, limit: int | None) -> list[dict]:
        """Fetch every document, paging on `document_id`.

        `search_after` on the `document_id` keyword rather than `from`/`size`:
        deep `from` paging is capped by `index.max_result_window` and would start
        silently dropping documents on exactly the large corpus this job exists
        for. `document_id` is a keyword and unique, so it is a total order and
        needs no tiebreaker.
        """
        collected: list[dict] = []
        search_after: list[Any] | None = None
        while True:
            page: dict[str, Any] = {
                "size": page_size,
                "_source": ["document_id", "content"],
                "query": {"match_all": {}},
                "sort": [{"document_id": "asc"}],
            }
            if search_after is not None:
                page["search_after"] = search_after
            response = self._request("POST", f"/{index}/_search", page)
            hits = response.get("hits", {}).get("hits", [])
            if not hits:
                break
            collected.extend(hits)
            if limit is not None and len(collected) >= limit:
                return collected[:limit]
            if len(hits) < page_size:
                break
            search_after = hits[-1].get("sort")
            if not search_after:
                break
        return collected

    def bulk_update(self, index: str, updates: list[tuple[str, dict[str, Any]]]) -> list[str]:
        """Partial-update documents; return the ids that failed.

        `_update` rather than `index`: this job owns one field and must not
        overwrite a projection written by live traffic.
        """
        if not updates:
            return []
        lines: list[str] = []
        for doc_id, doc in updates:
            lines.append(json.dumps({"update": {"_index": index, "_id": doc_id}}))
            lines.append(json.dumps({"doc": doc}))
        payload = "\n".join(lines) + "\n"
        response = self._request("POST", "/_bulk?refresh=wait_for", payload, ndjson=True)
        failures: list[str] = []
        if response.get("errors"):
            for item in response.get("items", []):
                action = item.get("update", {})
                if action.get("error"):
                    failures.append(f"{action.get('_id')}: {action['error'].get('reason')}")
        return failures


def run_backfill(
    client: OpenSearchClient,
    encoder: SparseEncoder,
    *,
    index: str,
    page_size: int,
    batch_size: int,
    limit: int | None,
    dry_run: bool,
) -> BackfillReport:
    report = BackfillReport()
    started = time.monotonic()

    if not client.mapping_has_sparse_field(index):
        raise RuntimeError(
            f"index '{index}' does not map '{SPARSE_FIELD}'. "
            "Add it to legal-search/api/src/core/opensearch/documents-index.mapping.ts, "
            "regenerate the JSON, and apply the mapping to the live index — this job "
            "deliberately does not create mappings, because a second writer to the "
            "documents mapping is how #675 and #713 happened."
        )

    hits = client.scroll_documents(index, page_size=page_size, limit=limit)
    report.scanned = len(hits)

    pending: list[tuple[str, str]] = []
    for hit in hits:
        source = hit.get("_source") or {}
        content = source.get("content")
        doc_id = hit.get("_id") or source.get("document_id") or "<unknown>"
        if not isinstance(content, str) or not content.strip():
            report.skipped_no_content.append(doc_id)
            continue
        pending.append((doc_id, content))

    for start in range(0, len(pending), batch_size):
        window = pending[start : start + batch_size]
        vectors = encoder.encode_documents([text for _, text in window], batch_size=batch_size)
        updates: list[tuple[str, dict[str, Any]]] = []
        for (doc_id, _), vector in zip(window, vectors, strict=True):
            if not vector:
                # Encoding produced nothing usable. Recording it as a failure is
                # the point: writing `{}` would index a document that can never
                # match, wearing the same shape as one that simply does not.
                report.failed.append(f"{doc_id}: encoder produced an empty sparse vector")
                continue
            report.embedded += 1
            updates.append((doc_id, {SPARSE_FIELD: vector}))

        if dry_run:
            for doc_id, doc in updates:
                logger.info("dry-run: would update %s with %d features", doc_id, len(doc[SPARSE_FIELD]))
            continue

        failures = client.bulk_update(index, updates)
        report.failed.extend(failures)
        report.updated += len(updates) - len(failures)

    report.elapsed_seconds = time.monotonic() - started
    return report


def build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(description="Backfill learned-sparse vectors onto indexed documents (ADR-0054).")
    parser.add_argument(
        "--opensearch-url",
        default="http://opensearch-cluster-master:9200",
        help="Base URL of the OpenSearch cluster.",
    )
    parser.add_argument(
        "--index",
        default=DEFAULT_INDEX,
        help=(
            "Index or alias to update. Defaults to the write alias, so reads keep "
            "serving whatever they served before this ran."
        ),
    )
    parser.add_argument("--model", default="BAAI/bge-m3")
    parser.add_argument("--device", default=None, help="cuda:0, cpu, ... (default: auto)")
    parser.add_argument("--page-size", type=int, default=100)
    parser.add_argument("--batch-size", type=int, default=4, help="Chunks per forward pass on the GPU.")
    parser.add_argument("--limit", type=int, default=None)
    parser.add_argument(
        "--dry-run",
        action="store_true",
        help="Encode and report, but write nothing.",
    )
    return parser


def main(argv: list[str] | None = None) -> int:
    logging.basicConfig(level=logging.INFO, format="%(levelname)s %(message)s")
    args = build_parser().parse_args(argv)

    client = OpenSearchClient(args.opensearch_url)
    encoder = SparseEncoder(args.model, device=args.device)

    try:
        report = run_backfill(
            client,
            encoder,
            index=args.index,
            page_size=args.page_size,
            batch_size=args.batch_size,
            limit=args.limit,
            dry_run=args.dry_run,
        )
    except (RuntimeError, urllib.error.URLError) as exc:
        logger.error("backfill failed: %s", exc)
        return 1

    print(json.dumps(report.as_dict(), indent=2))
    # A run that wrote nothing is not a success just because it did not crash.
    if report.failed:
        return 1
    return 0


if __name__ == "__main__":  # pragma: no cover
    sys.exit(main())
