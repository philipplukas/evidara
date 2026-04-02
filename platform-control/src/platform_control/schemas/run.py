from __future__ import annotations

from datetime import datetime

from pydantic import BaseModel, ConfigDict

from platform_control.domain import RunMode, RunStatus


class CreateRunRequest(BaseModel):
    source_id: str
    source_version_id: str
    mode: RunMode = RunMode.PREVIEW


class RunResponse(BaseModel):
    run_id: str
    source_id: str
    source_version_id: str
    mode: RunMode
    status: RunStatus
    started_at: datetime | None
    completed_at: datetime | None
    artifacts_count: int
    captured_resources_count: int
    failure_reason: str | None
    created_at: datetime
    updated_at: datetime

    model_config = ConfigDict(from_attributes=True)


class WebhookAcceptedResponse(BaseModel):
    status: str
