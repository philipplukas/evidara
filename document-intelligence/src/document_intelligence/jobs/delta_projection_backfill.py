"""Rebuild the legal-search OpenSearch index from canonical Delta (ADR-0005, issue #552).

ADR-0005 makes OpenSearch a *serving layer only*: the index is derived from canonical
truth (Delta) and "if an OpenSearch index is lost, corrupted, or needs changes, it is
rebuilt from canonical source". Until this job existed, the only rebuild path reindexed
OpenSearch *into* OpenSearch, so a lost index had nothing to read from — the corpus was
recoverable only by accident, via whatever ``document.processed`` events NATS JetStream
happened to still retain.

This job closes that: it walks ``published_documents`` on Delta, reconstructs the
``document.processed`` event each row would have produced, and POSTs it to the same
idempotent legal-search projections endpoint the live NATS bridge uses.

**Why it lives in document-intelligence.** The job needs two things: Delta/MinIO read
access, and the OpenSearch projection shape. DI already owns the first (``deltalake``,
``pyarrow``, ``DI_S3_*`` credentials); legal-search owns the second and there is no viable
Delta reader for Node. Rather than split the difference, this job reads Delta and hands
canonical rows to legal-search as ordinary events — so the projection shape stays owned by
``ProjectionsService`` and the backfill runs through the *exact* code path as live traffic.
No projection logic is duplicated here.

Operational properties (all inherited from the projections endpoint, not re-implemented):

- **Idempotent** — the projection upserts on ``document_id``, so re-running is a no-op that
  converges. Each emission carries a fresh ``event_id`` so a *surviving* projection-history
  index can never short-circuit a rebuild of an *empty* documents index.
- **Safe against live traffic** — writes land on the write alias; the read alias is
  untouched. If a live event has already projected a newer revision of a document, the
  endpoint's revision guard marks this backfill event ``stale`` and drops it, so a
  concurrent live update always wins the race.
- **Resumable** — documents are walked in ``document_id`` order and the last applied id is
  checkpointed, so an interrupted run continues with ``--resume``.

See ``docs/runbooks/projection-reindex-backfill.md`` for the recovery procedure.
"""

from __future__ import annotations

import argparse
import json
import logging
import os
import sys
import time
from collections.abc import Callable, Iterable, Iterator
from dataclasses import asdict, dataclass, field
from pathlib import Path
from typing import Any

from document_intelligence.config.runtime import RuntimeSettings
from document_intelligence.errors import ProcessingError
from document_intelligence.events.document_processed import (
    build_document_processed_event_from_published_row,
)
from document_intelligence.jobs.projection_bridge_consumer import (
    PermanentForwardError,
    post_projection_event,
)
from document_intelligence.service.store import DeltaPublishedDocumentStore

LOGGER = logging.getLogger("document_intelligence.delta_projection_backfill")

PROJECTION_EVENT_PATH = "/v1/projections/events/document-processed"
DEFAULT_CHECKPOINT_PATH = "/tmp/evidara-delta-projection-backfill.checkpoint"  # noqa: S108


@dataclass
class BackfillSummary:
    """Outcome of one backfill run (printed as JSON so operators can diff runs)."""

    scanned: int = 0
    applied: int = 0
    skipped_invalid: int = 0
    rejected: int = 0
    last_document_id: str | None = None
    dry_run: bool = False
    failed: bool = False
    failure_reason: str | None = None
    invalid_document_ids: list[str] = field(default_factory=list)

    def to_dict(self) -> dict[str, Any]:
        return asdict(self)


class FileCheckpoint:
    """Last-applied ``document_id``, persisted so an interrupted run can resume."""

    def __init__(self, path: Path) -> None:
        self._path = path

    def read(self) -> str | None:
        try:
            value = self._path.read_text(encoding="utf-8").strip()
        except FileNotFoundError:
            return None
        return value or None

    def record(self, document_id: str) -> None:
        self._path.parent.mkdir(parents=True, exist_ok=True)
        self._path.write_text(document_id, encoding="utf-8")

    def clear(self) -> None:
        self._path.unlink(missing_ok=True)


def backfill_rows(
    rows: Iterable[dict[str, Any]],
    *,
    post: Callable[[dict[str, Any]], None],
    on_applied: Callable[[str], None] | None = None,
    limit: int = 0,
    max_retries: int = 3,
    retry_backoff_seconds: float = 2.0,
    sleep: Callable[[float], None] = time.sleep,
    dry_run: bool = False,
    logger: logging.Logger = LOGGER,
) -> BackfillSummary:
    """Project canonical rows into legal-search, one ``document.processed`` event each.

    ``post`` raises :class:`PermanentForwardError` for a 4xx (the event is bad — count it and
    move on) and :class:`RuntimeError` for a transient 5xx/network failure (retried with
    backoff; exhausting retries fails the run so the operator sees it, while the checkpoint
    keeps the completed prefix so ``--resume`` picks up where it stopped).
    """
    summary = BackfillSummary(dry_run=dry_run)

    for row in rows:
        if limit and summary.scanned >= limit:
            break
        summary.scanned += 1

        try:
            event = build_document_processed_event_from_published_row(row)
        except ProcessingError as exc:
            summary.skipped_invalid += 1
            document_id = str(row.get("document_id") or "<unknown>")
            summary.invalid_document_ids.append(document_id)
            logger.warning(
                "backfill_row_invalid document_id=%s code=%s error=%s",
                document_id,
                exc.code,
                exc.summary,
            )
            continue

        document_id = str(event["payload"]["document_id"])

        if dry_run:
            summary.applied += 1
            summary.last_document_id = document_id
            logger.info("backfill_dry_run document_id=%s", document_id)
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
            # The projections endpoint rejected the event as invalid. Retrying is futile and
            # aborting would strand the rest of the corpus, so record and continue.
            summary.rejected += 1
            logger.warning("backfill_rejected document_id=%s error=%s", document_id, exc)
            continue
        except Exception as exc:
            summary.failed = True
            summary.failure_reason = f"{document_id}: {exc}"
            logger.error("backfill_failed document_id=%s error=%s", document_id, exc)
            return summary

        summary.applied += 1
        summary.last_document_id = document_id
        if on_applied is not None:
            on_applied(document_id)
        logger.info("backfill_applied document_id=%s", document_id)

    return summary


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
                "backfill_transient_retry document_id=%s attempt=%d/%d delay=%.1fs error=%s",
                event["payload"]["document_id"],
                attempt,
                max_retries,
                delay,
                exc,
            )
            sleep(delay)


def iter_canonical_rows(
    settings: RuntimeSettings,
    *,
    after_document_id: str | None = None,
) -> Iterator[dict[str, Any]]:
    """Enumerate the latest revision of every published document on canonical Delta."""
    if settings.surface_uris is None:
        raise ProcessingError(
            "missing_surface_config",
            "Delta backfill requires DI_SURFACES_ROOT_URI (or explicit DI_PUBLISHED_*_URI)",
        )
    store = DeltaPublishedDocumentStore(
        settings.surface_uris.published_documents_uri,
        settings.surface_uris.published_sections_uri,
    )
    return store.iter_latest_document_rows(after_document_id=after_document_id)


def _parse_args(argv: list[str] | None = None) -> argparse.Namespace:
    parser = argparse.ArgumentParser(
        prog="document_intelligence_delta_projection_backfill",
        description="Rebuild the legal-search search index from canonical Delta (ADR-0005).",
    )
    parser.add_argument(
        "--legal-search-api-url",
        default=os.environ.get("LEGAL_SEARCH_API_URL") or os.environ.get("NEXT_PUBLIC_API_URL"),
        help="legal-search API base URL (the projections endpoint is derived from it).",
    )
    parser.add_argument(
        "--legal-search-api-key",
        default=os.environ.get("LEGAL_SEARCH_API_KEY"),
        help="Optional X-API-Key for the legal-search projections endpoint.",
    )
    parser.add_argument(
        "--dry-run",
        action="store_true",
        help="Enumerate and build events but POST nothing.",
    )
    parser.add_argument("--limit", type=int, default=0, help="Stop after N documents (0 = all).")
    parser.add_argument(
        "--after-document-id",
        default=None,
        help="Resume from an explicit cursor (exclusive); documents are walked in document_id order.",
    )
    parser.add_argument(
        "--resume",
        action="store_true",
        help="Resume from the checkpoint file written by a previous run.",
    )
    parser.add_argument(
        "--checkpoint-path",
        default=os.environ.get("DI_BACKFILL_CHECKPOINT_PATH", DEFAULT_CHECKPOINT_PATH),
        help=f"Checkpoint file for --resume (default: {DEFAULT_CHECKPOINT_PATH}).",
    )
    parser.add_argument("--max-retries", type=int, default=3)
    parser.add_argument("--retry-backoff-seconds", type=float, default=2.0)
    parser.add_argument("--request-timeout-seconds", type=float, default=30.0)
    return parser.parse_args(argv)


def main(argv: list[str] | None = None) -> int:
    args = _parse_args(argv)
    logging.basicConfig(level=logging.INFO, format="%(asctime)s %(levelname)s %(message)s")

    if not args.dry_run and not args.legal_search_api_url:
        print("legal-search API URL is required (set LEGAL_SEARCH_API_URL)", file=sys.stderr)
        return 2

    checkpoint = FileCheckpoint(Path(args.checkpoint_path))
    after_document_id = args.after_document_id
    if args.resume and after_document_id is None:
        after_document_id = checkpoint.read()
        if after_document_id:
            LOGGER.info("resuming after document_id=%s", after_document_id)

    url = f"{str(args.legal_search_api_url or '').rstrip('/')}{PROJECTION_EVENT_PATH}"

    def post(event: dict[str, Any]) -> None:
        post_projection_event(
            url,
            json.dumps(event).encode("utf-8"),
            api_key=args.legal_search_api_key,
            timeout=args.request_timeout_seconds,
        )

    try:
        rows = iter_canonical_rows(
            RuntimeSettings.from_environment(),
            after_document_id=after_document_id,
        )
        summary = backfill_rows(
            rows,
            post=post,
            on_applied=None if args.dry_run else checkpoint.record,
            limit=args.limit,
            max_retries=args.max_retries,
            retry_backoff_seconds=args.retry_backoff_seconds,
            dry_run=args.dry_run,
        )
    except Exception as exc:
        LOGGER.exception("delta projection backfill failed")
        print(json.dumps({"status": "failed", "error": str(exc)}, indent=2), file=sys.stderr)
        return 1

    # A clean, complete run has nothing left to resume from.
    if not summary.failed and not summary.dry_run and not args.limit:
        checkpoint.clear()

    print(json.dumps(summary.to_dict(), indent=2, sort_keys=True))
    return 1 if summary.failed else 0


if __name__ == "__main__":
    raise SystemExit(main(sys.argv[1:]))
