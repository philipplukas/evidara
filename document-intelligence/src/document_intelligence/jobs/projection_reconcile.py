"""De-index search projections that canonical Delta no longer backs (ADR-0005, issue #652).

ADR-0005 makes OpenSearch a *serving layer only*: canonical Delta is the system of record
and "if an OpenSearch index is lost, corrupted, or needs changes, it is rebuilt from
canonical source". Keeping that claim true needs the diff in **both** directions, and only
one direction existed.

``document_intelligence_delta_projection_backfill`` covers *canonical minus index*: it
walks ``published_documents`` and re-projects every row. Because it is idempotent by
upsert on ``document_id``, it can only ever add or overwrite — it cannot delete. So an
index row whose canonical row is gone (an orphan from an earlier run, a document whose
identity key changed, a hand-poked test artifact) survives every rebuild and stays
user-visible forever. This job covers the other direction, *index minus canonical*.

How it works:

- **Index side** — pages ``GET /v1/projections/documents`` on legal-search. DI does not
  talk to OpenSearch: ADR-0008's repository-interface pattern makes ``legal-search/api``
  the sole owner of every OpenSearch call, so enumeration is a legal-search read endpoint
  and DI consumes it over HTTP. This mirrors the backfill, where DI owns Delta and hands
  canonical rows to legal-search as events.
- **Canonical side** — ``DeltaPublishedDocumentStore.iter_latest_document_rows``, the same
  enumeration the backfill uses.
- **Removal** — a ``document.withdrawn`` event per orphan, POSTed to the endpoint the live
  NATS bridge uses. legal-search's ``applyDocumentWithdrawn`` already deletes the
  projection, its sections and its citations, and already guards against withdrawing a
  document a newer live event has since re-projected. No delete logic is duplicated here.

Safety properties, because this is the one job in the repo that removes user-visible data:

- **Dry run by default.** Deleting requires an explicit ``--delete-orphans``; without it
  the job reports exactly what it would remove and exits.
- **Refuses to run against an empty canonical side.** A mistyped ``DI_SURFACES_ROOT_URI``
  reads as "canonical has nothing", which would mark the entire index orphaned. Zero
  canonical documents aborts before any deletion.
- **Refuses to delete more than ``--max-orphan-fraction`` of the index** (default 0.25)
  unless the operator raises the bound deliberately. Same failure mode, partial version.
- **Resumable** — orphans are walked in ``document_id`` order and the last withdrawn id is
  checkpointed, so an interrupted run continues with ``--resume``.

See ``docs/runbooks/projection-reindex-backfill.md`` for the operator procedure.
"""

from __future__ import annotations

import argparse
import json
import logging
import os
import sys
import time
import urllib.error
import urllib.parse
import urllib.request
from collections.abc import Callable, Iterable, Iterator
from dataclasses import asdict, dataclass, field
from pathlib import Path
from typing import Any

from document_intelligence.config.runtime import RuntimeSettings
from document_intelligence.errors import ProcessingError
from document_intelligence.events.document_withdrawn import (
    build_document_withdrawn_event_from_indexed_row,
)
from document_intelligence.jobs.delta_projection_backfill import (
    FileCheckpoint,
    iter_canonical_rows,
)
from document_intelligence.jobs.projection_bridge_consumer import (
    PermanentForwardError,
    post_projection_event,
)

LOGGER = logging.getLogger("document_intelligence.projection_reconcile")

INDEXED_DOCUMENTS_PATH = "/v1/projections/documents"
WITHDRAWN_EVENT_PATH = "/v1/projections/events/document-withdrawn"
DEFAULT_CHECKPOINT_PATH = "/tmp/evidara-projection-reconcile.checkpoint"  # noqa: S108
DEFAULT_PAGE_SIZE = 500
DEFAULT_MAX_ORPHAN_FRACTION = 0.25


@dataclass
class ReconcileSummary:
    """Outcome of one reconcile run (printed as JSON so operators can diff runs)."""

    indexed_scanned: int = 0
    canonical_documents: int = 0
    orphaned: int = 0
    deleted: int = 0
    skipped_unwithdrawable: int = 0
    rejected: int = 0
    last_document_id: str | None = None
    dry_run: bool = True
    failed: bool = False
    failure_reason: str | None = None
    orphan_document_ids: list[str] = field(default_factory=list)
    unwithdrawable_document_ids: list[str] = field(default_factory=list)

    def to_dict(self) -> dict[str, Any]:
        return asdict(self)


def iter_indexed_documents(
    base_url: str,
    *,
    api_key: str | None = None,
    page_size: int = DEFAULT_PAGE_SIZE,
    after_document_id: str | None = None,
    timeout: float = 30.0,
    fetch_page: Callable[[str], dict[str, Any]] | None = None,
) -> Iterator[dict[str, Any]]:
    """Page ``GET /v1/projections/documents`` until the cursor runs out.

    ``fetch_page`` is injectable so the walk is unit-testable without an HTTP server.
    """
    getter = fetch_page or (lambda url: _get_json(url, api_key=api_key, timeout=timeout))
    cursor = after_document_id
    while True:
        params: dict[str, str] = {"limit": str(page_size)}
        if cursor:
            params["after"] = cursor
        url = f"{base_url.rstrip('/')}{INDEXED_DOCUMENTS_PATH}?{urllib.parse.urlencode(params)}"

        page = getter(url)
        rows = page.get("data")
        if not isinstance(rows, list):
            raise ProcessingError(
                "reconcile_enumeration_invalid",
                f"{url} returned no `data` array",
            )
        for row in rows:
            if isinstance(row, dict):
                yield row

        next_after = page.get("next_after")
        if not isinstance(next_after, str) or not next_after:
            return
        if cursor is not None and next_after <= cursor:
            # The cursor must strictly advance; anything else is an infinite loop.
            raise ProcessingError(
                "reconcile_enumeration_invalid",
                f"cursor did not advance ({cursor!r} -> {next_after!r})",
            )
        cursor = next_after


def reconcile_documents(
    indexed_rows: Iterable[dict[str, Any]],
    canonical_document_ids: set[str],
    *,
    post: Callable[[dict[str, Any]], None],
    on_deleted: Callable[[str], None] | None = None,
    delete_orphans: bool = False,
    reason_summary: str = "reconcile: no canonical published_documents row (ADR-0005)",
    limit: int = 0,
    max_retries: int = 3,
    retry_backoff_seconds: float = 2.0,
    sleep: Callable[[float], None] = time.sleep,
    logger: logging.Logger = LOGGER,
) -> ReconcileSummary:
    """Diff the indexed rows against canonical ids and withdraw what canonical does not back.

    ``delete_orphans=False`` (the default) reports the diff and posts nothing, so an
    operator always sees what *would* be removed before anything is.
    """
    summary = ReconcileSummary(
        dry_run=not delete_orphans,
        canonical_documents=len(canonical_document_ids),
    )

    for row in indexed_rows:
        if limit and summary.indexed_scanned >= limit:
            break
        summary.indexed_scanned += 1

        document_id = row.get("document_id")
        if not isinstance(document_id, str) or not document_id:
            continue
        if document_id in canonical_document_ids:
            continue

        summary.orphaned += 1
        summary.orphan_document_ids.append(document_id)

        try:
            event = build_document_withdrawn_event_from_indexed_row(
                row,
                reason_summary=reason_summary,
            )
        except ProcessingError as exc:
            # The index row lacks the provenance a contract-valid withdrawal needs. Guessing
            # would put invented ids into projection-history, so the row is reported instead
            # — the operator gets an exact list to remove by hand.
            summary.skipped_unwithdrawable += 1
            summary.unwithdrawable_document_ids.append(document_id)
            logger.warning(
                "reconcile_unwithdrawable document_id=%s title=%r code=%s error=%s",
                document_id,
                row.get("title"),
                exc.code,
                exc.summary,
            )
            continue

        if not delete_orphans:
            logger.info(
                "reconcile_dry_run_orphan document_id=%s title=%r",
                document_id,
                row.get("title"),
            )
            summary.last_document_id = document_id
            continue

        try:
            _post_with_retries(
                event,
                post=post,
                max_retries=max_retries,
                retry_backoff_seconds=retry_backoff_seconds,
                sleep=sleep,
                logger=logger,
            )
        except PermanentForwardError as exc:
            # legal-search rejected the withdrawal as invalid. Retrying is futile and
            # aborting would strand the rest of the diff, so record and continue.
            summary.rejected += 1
            logger.warning("reconcile_rejected document_id=%s error=%s", document_id, exc)
            continue
        except Exception as exc:
            summary.failed = True
            summary.failure_reason = f"{document_id}: {exc}"
            logger.error("reconcile_failed document_id=%s error=%s", document_id, exc)
            return summary

        summary.deleted += 1
        summary.last_document_id = document_id
        if on_deleted is not None:
            on_deleted(document_id)
        logger.info("reconcile_deleted document_id=%s title=%r", document_id, row.get("title"))

    return summary


def check_delete_guardrails(
    summary: ReconcileSummary,
    *,
    max_orphan_fraction: float,
) -> str | None:
    """Return a refusal reason when the diff looks like a misconfiguration, else ``None``.

    The catastrophic failure of this job is not deleting one wrong document — it is a
    canonical side that reads as empty or near-empty (wrong ``DI_SURFACES_ROOT_URI``,
    unreadable object store, half-written table) making the whole index look orphaned.
    Both guards below describe that shape.
    """
    if summary.canonical_documents == 0:
        return (
            "canonical Delta enumerated 0 documents — refusing to treat the entire index "
            "as orphaned; check DI_SURFACES_ROOT_URI / DI_S3_* and re-run"
        )
    if summary.indexed_scanned == 0:
        return None
    fraction = summary.orphaned / summary.indexed_scanned
    if fraction > max_orphan_fraction:
        return (
            f"{summary.orphaned}/{summary.indexed_scanned} indexed documents "
            f"({fraction:.0%}) have no canonical row, above --max-orphan-fraction "
            f"{max_orphan_fraction:.0%}. Review the dry-run list; raise the bound "
            f"deliberately if this is expected."
        )
    return None


def _post_with_retries(
    event: dict[str, Any],
    *,
    post: Callable[[dict[str, Any]], None],
    max_retries: int,
    retry_backoff_seconds: float,
    sleep: Callable[[float], None],
    logger: logging.Logger,
) -> None:
    attempt = 0
    while True:
        try:
            post(event)
            return
        except PermanentForwardError:
            raise
        except Exception as exc:
            attempt += 1
            if attempt > max_retries:
                raise
            delay = retry_backoff_seconds * attempt
            logger.warning(
                "reconcile_transient_retry document_id=%s attempt=%d/%d delay=%.1fs error=%s",
                event["payload"]["document_id"],
                attempt,
                max_retries,
                delay,
                exc,
            )
            sleep(delay)


def _get_json(url: str, *, api_key: str | None, timeout: float) -> dict[str, Any]:
    headers = {"Accept": "application/json"}
    if api_key:
        headers["X-API-Key"] = api_key
    request = urllib.request.Request(url, headers=headers, method="GET")  # noqa: S310
    try:
        with urllib.request.urlopen(request, timeout=timeout) as response:  # noqa: S310
            payload = json.loads(response.read().decode("utf-8"))
    except urllib.error.HTTPError as exc:
        body = exc.read().decode("utf-8", errors="replace")
        raise RuntimeError(f"GET {url} failed {exc.code}: {body}") from exc
    except urllib.error.URLError as exc:
        raise RuntimeError(f"GET {url} network error: {exc.reason}") from exc
    if not isinstance(payload, dict):
        raise ProcessingError("reconcile_enumeration_invalid", f"{url} returned a non-object body")
    return payload


def collect_canonical_document_ids(settings: RuntimeSettings) -> set[str]:
    """Every ``document_id`` with a latest canonical revision on Delta."""
    return {str(row["document_id"]) for row in iter_canonical_rows(settings) if isinstance(row.get("document_id"), str)}


def _parse_args(argv: list[str] | None = None) -> argparse.Namespace:
    parser = argparse.ArgumentParser(
        prog="document_intelligence_projection_reconcile",
        description=(
            "De-index search projections with no canonical Delta row (ADR-0005). "
            "Dry-run unless --delete-orphans is given."
        ),
    )
    parser.add_argument(
        "--legal-search-api-url",
        default=os.environ.get("LEGAL_SEARCH_API_URL") or os.environ.get("NEXT_PUBLIC_API_URL"),
        help="legal-search API base URL (enumeration and withdrawal paths derive from it).",
    )
    parser.add_argument(
        "--legal-search-api-key",
        default=os.environ.get("LEGAL_SEARCH_API_KEY"),
        help="Optional X-API-Key for the legal-search projections endpoints.",
    )
    parser.add_argument(
        "--delete-orphans",
        action="store_true",
        help=(
            "ACTUALLY DELETE. Without this the job only reports what it would remove. "
            "Deleted documents disappear from search immediately."
        ),
    )
    parser.add_argument(
        "--max-orphan-fraction",
        type=float,
        default=DEFAULT_MAX_ORPHAN_FRACTION,
        help=(
            "Refuse to delete when more than this fraction of the index is orphaned "
            f"(default {DEFAULT_MAX_ORPHAN_FRACTION}). A near-1.0 diff usually means the "
            "canonical side is misconfigured, not that the index is wrong."
        ),
    )
    parser.add_argument("--page-size", type=int, default=DEFAULT_PAGE_SIZE, help="Index enumeration page size.")
    parser.add_argument("--limit", type=int, default=0, help="Stop after N indexed docs (0 = all).")
    parser.add_argument(
        "--after-document-id",
        default=None,
        help="Resume from an explicit cursor (exclusive); documents walk in document_id order.",
    )
    parser.add_argument(
        "--resume",
        action="store_true",
        help="Resume from the checkpoint file written by a previous run.",
    )
    parser.add_argument(
        "--checkpoint-path",
        default=os.environ.get("DI_RECONCILE_CHECKPOINT_PATH", DEFAULT_CHECKPOINT_PATH),
        help=f"Checkpoint file for --resume (default: {DEFAULT_CHECKPOINT_PATH}).",
    )
    parser.add_argument("--max-retries", type=int, default=3)
    parser.add_argument("--retry-backoff-seconds", type=float, default=2.0)
    parser.add_argument("--request-timeout-seconds", type=float, default=30.0)
    return parser.parse_args(argv)


def main(argv: list[str] | None = None) -> int:
    args = _parse_args(argv)
    logging.basicConfig(level=logging.INFO, format="%(asctime)s %(levelname)s %(message)s")

    if not args.legal_search_api_url:
        # Unlike the backfill, even a dry run needs legal-search: the index side of the
        # diff can only be read from it.
        print("legal-search API URL is required (set LEGAL_SEARCH_API_URL)", file=sys.stderr)
        return 2

    base_url = str(args.legal_search_api_url).rstrip("/")
    checkpoint = FileCheckpoint(Path(args.checkpoint_path))
    after_document_id = args.after_document_id
    if args.resume and after_document_id is None:
        after_document_id = checkpoint.read()
        if after_document_id:
            LOGGER.info("resuming after document_id=%s", after_document_id)

    def post(event: dict[str, Any]) -> None:
        post_projection_event(
            f"{base_url}{WITHDRAWN_EVENT_PATH}",
            json.dumps(event).encode("utf-8"),
            api_key=args.legal_search_api_key,
            timeout=args.request_timeout_seconds,
        )

    try:
        canonical_ids = collect_canonical_document_ids(RuntimeSettings.from_environment())

        # Pass 1 always runs as a dry run so the guardrails see the whole diff before a
        # single document is removed. Deleting straight through would mean the refusal
        # arrives after the damage.
        preview = reconcile_documents(
            iter_indexed_documents(
                base_url,
                api_key=args.legal_search_api_key,
                page_size=args.page_size,
                after_document_id=after_document_id,
                timeout=args.request_timeout_seconds,
            ),
            canonical_ids,
            post=post,
            delete_orphans=False,
            limit=args.limit,
        )

        if not args.delete_orphans:
            print(json.dumps(preview.to_dict(), indent=2, sort_keys=True))
            return 0

        refusal = check_delete_guardrails(preview, max_orphan_fraction=args.max_orphan_fraction)
        if refusal is not None:
            LOGGER.error("reconcile_refused %s", refusal)
            preview.failed = True
            preview.failure_reason = refusal
            print(json.dumps(preview.to_dict(), indent=2, sort_keys=True), file=sys.stderr)
            return 1

        summary = reconcile_documents(
            iter_indexed_documents(
                base_url,
                api_key=args.legal_search_api_key,
                page_size=args.page_size,
                after_document_id=after_document_id,
                timeout=args.request_timeout_seconds,
            ),
            canonical_ids,
            post=post,
            on_deleted=checkpoint.record,
            delete_orphans=True,
            limit=args.limit,
            max_retries=args.max_retries,
            retry_backoff_seconds=args.retry_backoff_seconds,
        )
    except Exception as exc:
        LOGGER.exception("projection reconcile failed")
        print(json.dumps({"status": "failed", "error": str(exc)}, indent=2), file=sys.stderr)
        return 1

    # A clean, complete run has nothing left to resume from.
    if not summary.failed and not args.limit:
        checkpoint.clear()

    print(json.dumps(summary.to_dict(), indent=2, sort_keys=True))
    return 1 if summary.failed else 0


if __name__ == "__main__":
    raise SystemExit(main(sys.argv[1:]))
