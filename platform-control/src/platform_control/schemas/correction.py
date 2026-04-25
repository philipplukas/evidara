from __future__ import annotations

from datetime import datetime
from typing import Any

from pydantic import BaseModel, ConfigDict, Field

from platform_control.domain import (
    CorrectionStatus,
    CorrectionTargetEntityType,
    CorrectionType,
)


class CorrectionResponse(BaseModel):
    """Operator-facing view of a stored correction row."""

    correction_id: str
    target_entity_type: CorrectionTargetEntityType
    target_entity_id: str
    correction_type: CorrectionType
    payload: dict[str, Any]
    original_snapshot: dict[str, Any]
    operator_id: str | None
    pipeline_run_id: str | None
    rationale: str | None
    status: CorrectionStatus
    source_correction_id: str | None = None
    workflow_id: str | None = None
    workflow_run_id: str | None = None
    resulting_run_id: str | None = None
    resulting_extraction_id: str | None = None
    completed_at: datetime | None = None
    created_at: datetime
    applied_at: datetime | None

    model_config = ConfigDict(from_attributes=True)


class CorrectionListResponse(BaseModel):
    data: list[CorrectionResponse]
    next_cursor: str | None = None


class CorrectionQueueQuery(BaseModel):
    """Filter envelope for the queue endpoint."""

    target_entity_type: CorrectionTargetEntityType | None = None
    correction_type: CorrectionType | None = None
    status: CorrectionStatus = CorrectionStatus.PENDING
    limit: int = Field(default=50, ge=1, le=500)
    cursor: str | None = None


class RescoreRequest(BaseModel):
    """Body for ``POST /v1/corrections/{correction_id}/rescore`` (#427).

    Both fields are optional. ``rationale`` is captured on the audit row.
    ``dry_run`` is forwarded to the workflow so the targeted re-extraction
    skips the persistence step (useful when an operator wants to compare
    candidate extractions without writing them).
    """

    rationale: str | None = Field(default=None, max_length=2000)
    dry_run: bool = False

    model_config = ConfigDict(extra="forbid")


class RescoreResponse(BaseModel):
    """Response for the rescore endpoint (#427).

    Returned with HTTP 202 — the workflow runs asynchronously. ``run_id``
    here is the *Temporal* run id (the per-execution identifier inside a
    workflow), not a platform-control ``Run`` id; the latter is recorded as
    ``resulting_run_id`` on the correction once the workflow completes.
    """

    rescore_correction_id: str
    workflow_id: str
    run_id: str | None = None

    model_config = ConfigDict(extra="forbid")
