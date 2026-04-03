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


class RunPreviewSummarySample(BaseModel):
    captured_resource_id: str
    title: str | None
    final_url: str
    content_type: str
    http_status: int | None
    reason: str


class RunPreviewSummaryBreakdownEntry(BaseModel):
    content_type: str
    count: int


class RunPreviewSummaryDriftCheck(BaseModel):
    name: str
    status: str
    detail: str


class RunPreviewSummaryResponse(BaseModel):
    run_id: str
    captured_url_count: int
    artifacts_count: int
    captured_resources_count: int
    pdf_count: int
    likely_decision_page_count: int
    likely_boilerplate_page_count: int
    likely_duplicate_page_count: int
    content_type_breakdown: list[RunPreviewSummaryBreakdownEntry]
    likely_decision_pages: list[RunPreviewSummarySample]
    likely_boilerplate_pages: list[RunPreviewSummarySample]
    likely_duplicate_pages: list[RunPreviewSummarySample]
    drift_checks: list[RunPreviewSummaryDriftCheck]
