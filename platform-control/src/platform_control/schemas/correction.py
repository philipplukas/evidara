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
    operator_id: str
    pipeline_run_id: str | None
    rationale: str | None
    status: CorrectionStatus
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
