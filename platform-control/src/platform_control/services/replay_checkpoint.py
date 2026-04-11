"""Persisted replay frontier snapshots for acquisition runs (run metadata)."""

from __future__ import annotations

from datetime import UTC, datetime
from typing import Any

from sqlalchemy.orm.attributes import flag_modified

from platform_control.models.run import Run

REPLAY_CHECKPOINT_SCHEMA_VERSION = 1


def merge_run_replay_checkpoint(
    run: Run,
    *,
    last_firecrawl_event_type: str | None = None,
    pages_ingested: int | None = None,
    extra: dict[str, Any] | None = None,
) -> None:
    """Merge fields into ``metadata.replay_checkpoint`` and mark JSON dirty for ORM."""
    md = dict(run.run_metadata or {})
    prev = dict(md.get("replay_checkpoint") or {})
    prev.setdefault("schema_version", REPLAY_CHECKPOINT_SCHEMA_VERSION)
    if last_firecrawl_event_type is not None:
        prev["last_firecrawl_event_type"] = last_firecrawl_event_type
    if pages_ingested is not None:
        prev["pages_ingested"] = pages_ingested
    if extra:
        for key, value in extra.items():
            if value is not None:
                prev[key] = value
    prev["updated_at"] = datetime.now(UTC).isoformat()
    md["replay_checkpoint"] = prev
    run.run_metadata = md
    flag_modified(run, "run_metadata")


def checkpoint_dict_from_parent(parent: Run | None) -> dict[str, Any] | None:
    """Return a copy of the parent's checkpoint for child replay runs, if any."""
    if parent is None:
        return None
    raw = (parent.run_metadata or {}).get("replay_checkpoint")
    if isinstance(raw, dict) and raw:
        return dict(raw)
    return None
