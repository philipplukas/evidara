"""Response schemas for the run lifecycle timeline endpoint."""

from __future__ import annotations

from datetime import datetime
from enum import StrEnum

from pydantic import BaseModel, ConfigDict


class TimelineEntryKind(StrEnum):
    RUN = "run"
    PROCESSING_STATUS = "processing_status"
    DOCUMENT_LIFECYCLE = "document_lifecycle"


class TimelineEntry(BaseModel):
    """A single event in the run lifecycle timeline."""

    kind: TimelineEntryKind
    event_id: str | None = None
    occurred_at: datetime
    summary: str

    # Processing-status fields (present when kind == processing_status)
    processing_manifest_id: str | None = None
    processing_version: str | None = None
    status: str | None = None
    document_id: str | None = None
    document_revision: int | None = None
    error_code: str | None = None
    error_summary: str | None = None

    # Document-lifecycle fields (present when kind == document_lifecycle)
    event_type: str | None = None
    lifecycle_status: str | None = None
    reason_code: str | None = None
    reason_summary: str | None = None
    search_disposition: str | None = None


class RunLifecycleResponse(BaseModel):
    """Aggregated timeline for a single run."""

    run_id: str
    source_id: str
    source_version_id: str
    run_status: str
    started_at: datetime | None
    completed_at: datetime | None
    timeline: list[TimelineEntry]
    counts: RunLifecycleCounts

    model_config = ConfigDict(from_attributes=True)


class RunLifecycleCounts(BaseModel):
    processing_status_updates: int
    document_lifecycle_events: int
