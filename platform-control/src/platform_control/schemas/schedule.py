from __future__ import annotations

from datetime import datetime

from pydantic import BaseModel, ConfigDict, Field, field_validator

from platform_control.domain import RunMode

# An acceptance run is a deliberate, one-shot rehearsal an operator drives in
# order to produce ADR-0030 evidence. It reaches a live portal on a provider
# with no acceptance evidence and — for AWAITING_EVIDENCE providers — waives the
# config key. Scheduling one would turn that single rehearsal into permanent,
# unattended crawling that the operator key can no longer stop, which is the
# opposite of what the mode is for. `schedule_evaluator` stamps the schedule's
# mode straight onto a Run without passing `_require_launchable`, so the boundary
# has to be here.
_SCHEDULABLE_MODES = frozenset({RunMode.PREVIEW, RunMode.PRODUCTION})


def _reject_unschedulable_mode(mode: RunMode | None) -> RunMode | None:
    if mode is not None and mode not in _SCHEDULABLE_MODES:
        raise ValueError(
            f"mode={mode.value!r} cannot be scheduled. An acceptance run is a one-shot "
            "operator rehearsal that produces ADR-0030 evidence; dispatch it directly "
            "against /v1/runs instead."
        )
    return mode


class CreateScheduleRequest(BaseModel):
    source_id: str
    source_version_id: str
    cron_expression: str = Field(
        ...,
        pattern=r"^[\d\*\/\-\,\?\#LW ]+$",
        description="Standard cron expression (5 fields: min hour dom month dow)",
        examples=["0 2 * * *", "0 */6 * * *"],
    )
    timezone: str = Field(default="UTC", examples=["UTC", "Europe/Zurich"])
    mode: RunMode = RunMode.PRODUCTION
    enabled: bool = True
    description: str | None = None

    model_config = ConfigDict(extra="forbid")

    @field_validator("mode")
    @classmethod
    def _mode_is_schedulable(cls, mode: RunMode) -> RunMode:
        return _reject_unschedulable_mode(mode)


class UpdateScheduleRequest(BaseModel):
    cron_expression: str | None = Field(
        default=None,
        pattern=r"^[\d\*\/\-\,\?\#LW ]+$",
    )
    timezone: str | None = None
    mode: RunMode | None = None
    enabled: bool | None = None
    description: str | None = None

    model_config = ConfigDict(extra="forbid")

    @field_validator("mode")
    @classmethod
    def _mode_is_schedulable(cls, mode: RunMode | None) -> RunMode | None:
        return _reject_unschedulable_mode(mode)


class ScheduleResponse(BaseModel):
    schedule_id: str
    source_id: str
    source_version_id: str
    cron_expression: str
    timezone: str
    mode: RunMode
    enabled: bool
    description: str | None
    last_triggered_at: datetime | None
    last_run_id: str | None
    created_at: datetime
    updated_at: datetime

    model_config = ConfigDict(from_attributes=True)


class ScheduleListResponse(BaseModel):
    data: list[ScheduleResponse]
