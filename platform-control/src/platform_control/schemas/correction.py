"""Pydantic schemas for the corrections HITL surface.

Mirrors `contracts/schemas/corrections.json` (PR #434) and the
OpenAPI shapes attached to `/v1/corrections` in
`contracts/api/platform-control.openapi.yaml`. The on-disk JSON Schema
remains the canonical wire shape; this module is the runtime
counterpart consumed by FastAPI + ValidationPipe-equivalent logic.
"""

from __future__ import annotations

from datetime import datetime
from enum import StrEnum
from typing import Any

from pydantic import BaseModel, ConfigDict, Field

_CORRECTION_ID_RE = r"^cor_[a-z0-9]+$"
_OPERATOR_ID_RE = r"^op_[a-z0-9]+$"
_PIPELINE_RUN_ID_RE = r"^run_[a-z0-9]+$"
_SOURCE_ID_RE = r"^src_[a-z0-9]+$"
_DOCUMENT_ID_RE = r"^doc_[0-9a-hjkmnp-tv-z]{26}$"
_INSIGHT_ID_RE = r"^ins_[0-9a-hjkmnp-tv-z]{26}$"


class TargetEntityType(StrEnum):
    SOURCE = "source"
    DOCUMENT = "document"
    COMMENTARY_INSIGHT = "commentary_insight"


class CorrectionType(StrEnum):
    FIELD_EDIT = "field_edit"
    ANNOTATION = "annotation"
    REJECT = "reject"
    RESCORE_REQUEST = "rescore_request"


class CorrectionStatus(StrEnum):
    PENDING = "pending"
    APPLIED = "applied"
    REJECTED = "rejected"
    SUPERSEDED = "superseded"


def _validate_target_id(target_type: TargetEntityType, target_id: str) -> None:
    """Validate `target_entity_id` matches the family implied by `target_entity_type`.

    Mirrors the conditional `if/then` rules in
    `contracts/schemas/corrections.json` so the runtime fails the same way
    the schema validator would.
    """

    import re

    pattern: str
    if target_type is TargetEntityType.SOURCE:
        pattern = _SOURCE_ID_RE
    elif target_type is TargetEntityType.DOCUMENT:
        pattern = _DOCUMENT_ID_RE
    elif target_type is TargetEntityType.COMMENTARY_INSIGHT:
        pattern = _INSIGHT_ID_RE
    else:  # pragma: no cover — exhaustive
        raise ValueError(f"Unknown target_entity_type: {target_type}")
    if not re.match(pattern, target_id):
        raise ValueError(
            f"target_entity_id {target_id!r} does not match the pattern required by "
            f"target_entity_type={target_type.value} ({pattern})."
        )


class CreateCorrectionRequest(BaseModel):
    target_entity_type: TargetEntityType
    target_entity_id: str = Field(min_length=1)
    correction_type: CorrectionType
    payload: dict[str, Any]
    original_snapshot: dict[str, Any] | None = None
    pipeline_run_id: str | None = Field(default=None, pattern=_PIPELINE_RUN_ID_RE)
    rationale: str | None = Field(default=None, max_length=2000)

    model_config = ConfigDict(extra="forbid")

    def model_post_init(self, _ctx: Any) -> None:
        _validate_target_id(self.target_entity_type, self.target_entity_id)


class UpdateCorrectionStatusRequest(BaseModel):
    """Status-transition request body.

    `pending` is intentionally NOT in the input enum — `pending` is the
    initial status set on creation; transitioning *back* to pending is
    not a legal move.
    """

    status: CorrectionStatus
    rationale: str | None = Field(default=None, max_length=2000)

    model_config = ConfigDict(extra="forbid")

    def model_post_init(self, _ctx: Any) -> None:
        if self.status is CorrectionStatus.PENDING:
            raise ValueError(
                "Cannot transition correction status back to 'pending'. "
                "Allowed targets: applied, rejected, superseded."
            )


class CorrectionResponse(BaseModel):
    correction_id: str = Field(pattern=_CORRECTION_ID_RE)
    target_entity_type: TargetEntityType
    target_entity_id: str
    correction_type: CorrectionType
    payload: dict[str, Any]
    original_snapshot: dict[str, Any] | None
    operator_id: str = Field(pattern=_OPERATOR_ID_RE)
    pipeline_run_id: str | None
    rationale: str | None
    status: CorrectionStatus
    created_at: datetime
    applied_at: datetime | None

    model_config = ConfigDict(from_attributes=True)


class CorrectionListResponse(BaseModel):
    data: list[CorrectionResponse]
    total: int | None = None
    limit: int | None = None
    offset: int | None = None


class WeeklyBucket(BaseModel):
    """A single week aggregation bucket. `week_start` is the ISO date of
    the Monday of the bucket; `count` is the number of matching rows."""

    week_start: str = Field(pattern=r"^\d{4}-\d{2}-\d{2}$")
    count: int = Field(ge=0)


class GroupedWeeklySeries(BaseModel):
    """Weekly series for one group key (target_entity_type or correction_type)."""

    key: str
    buckets: list[WeeklyBucket]


class OperatorThroughputEntry(BaseModel):
    operator_id: str = Field(pattern=_OPERATOR_ID_RE)
    total: int = Field(ge=0)
    applied: int = Field(ge=0)
    rejected: int = Field(ge=0)


class RescoreOutcomeCounts(BaseModel):
    """Outcome counts for `rescore_request` corrections.

    Until the rescore lane (#427) lands, `changed` / `unchanged` / `failed`
    are populated from the correction status alone (`applied` → counted in
    aggregate, no per-outcome data yet). `pending` and `rejected` are
    always live from the corrections audit log.
    """

    pending: int = Field(ge=0)
    applied_total: int = Field(ge=0)
    rejected: int = Field(ge=0)
    # Forward-looking: populated by #427 when the rescore worker writes
    # back the run outcome on the correction's payload. Zero until then.
    changed: int = Field(ge=0)
    unchanged: int = Field(ge=0)
    failed: int = Field(ge=0)


class CorrectionMetricsResponse(BaseModel):
    """Aggregate read model for the admin dashboard (#432).

    Computed entirely from the `corrections` audit log — no new
    telemetry store required for v1.
    """

    window_weeks: int = Field(ge=1, le=52)
    operator_throughput_window_days: int = Field(ge=1, le=365)
    weekly_by_target_entity_type: list[GroupedWeeklySeries]
    weekly_by_correction_type: list[GroupedWeeklySeries]
    operator_throughput: list[OperatorThroughputEntry]
    rescore_outcomes: RescoreOutcomeCounts
