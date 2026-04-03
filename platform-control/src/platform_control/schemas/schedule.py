from __future__ import annotations

from datetime import datetime

from pydantic import BaseModel, ConfigDict, Field

from platform_control.domain import RunMode


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
