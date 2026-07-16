from __future__ import annotations

from datetime import datetime
from typing import Any

from pydantic import BaseModel, ConfigDict, Field, HttpUrl, model_validator

from platform_control.domain import (
    ProviderJobStatus,
    RunMode,
    RunReplayMode,
    RunScopeKind,
    RunStatus,
)


class RunScopeRequest(BaseModel):
    kind: RunScopeKind = RunScopeKind.FULL_SOURCE
    source_snapshot_id: str | None = Field(default=None, pattern=r"^snap_[a-z0-9]+$")
    captured_resource_ids: list[str] = Field(default_factory=list)
    include_urls: list[HttpUrl] = Field(default_factory=list)
    since: datetime | None = None
    until: datetime | None = None
    max_resources: int | None = Field(default=None, ge=1, le=10000)

    model_config = ConfigDict(extra="forbid")

    @model_validator(mode="after")
    def validate_scope(self) -> RunScopeRequest:
        if self.kind is RunScopeKind.FULL_SOURCE:
            if any(
                [
                    self.source_snapshot_id,
                    self.captured_resource_ids,
                    self.include_urls,
                    self.since,
                    self.until,
                    self.max_resources,
                ]
            ):
                raise ValueError("full_source scope cannot include narrowing fields")
        elif self.kind is RunScopeKind.SOURCE_SNAPSHOT:
            if not self.source_snapshot_id:
                raise ValueError("source_snapshot scope requires source_snapshot_id")
        elif self.kind is RunScopeKind.DISCOVERED_SUBSET:
            if not (
                self.captured_resource_ids or self.include_urls or self.max_resources is not None
            ):
                raise ValueError(
                    "discovered_subset scope requires captured_resource_ids, "
                    "include_urls, or max_resources"
                )
        elif self.kind is RunScopeKind.TIME_WINDOW:
            if not (self.since or self.until):
                raise ValueError("time_window scope requires since or until")

        if self.since and self.until and self.since > self.until:
            raise ValueError("scope since must be earlier than or equal to until")
        return self


class RunReplayRequest(BaseModel):
    mode: RunReplayMode
    parent_run_id: str | None = Field(default=None, pattern=r"^run_[a-z0-9]+$")
    reason: str | None = None

    model_config = ConfigDict(extra="forbid")

    @model_validator(mode="after")
    def validate_replay(self) -> RunReplayRequest:
        if self.mode in {RunReplayMode.PARTIAL_RERUN, RunReplayMode.FULL_REFRESH}:
            if not self.parent_run_id:
                raise ValueError(f"{self.mode.value} replay requires parent_run_id")
        return self


class CreateRunRequest(BaseModel):
    source_id: str
    source_version_id: str
    mode: RunMode = RunMode.PREVIEW
    scope: RunScopeRequest = Field(default_factory=RunScopeRequest)
    replay: RunReplayRequest | None = None

    model_config = ConfigDict(extra="forbid")


class RunResponse(BaseModel):
    run_id: str = Field(examples=["run_01hzxk9c4dnpf8h6t2m5q7w3"])
    source_id: str
    source_version_id: str
    mode: RunMode
    scope: RunScopeRequest
    replay: RunReplayRequest | None
    replay_checkpoint: dict[str, Any] | None = None
    status: RunStatus
    started_at: datetime | None
    completed_at: datetime | None
    artifacts_count: int
    captured_resources_count: int
    failure_reason: str | None
    created_at: datetime
    updated_at: datetime

    model_config = ConfigDict(from_attributes=True)


class RunListItemResponse(BaseModel):
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
    source_name: str
    version_label: str


class RunListResponse(BaseModel):
    data: list[RunListItemResponse]
    total: int | None = None
    limit: int | None = None
    offset: int | None = None


class RunReadinessCheck(BaseModel):
    code: str
    ok: bool
    detail: str

    model_config = ConfigDict(extra="forbid")


class RunReadinessResponse(BaseModel):
    source_id: str
    source_version_id: str
    mode: RunMode
    ready: bool
    checks: list[RunReadinessCheck]

    model_config = ConfigDict(extra="forbid")


class CapturedResourceResponse(BaseModel):
    captured_resource_id: str
    run_id: str
    source_url: str
    final_url: str
    title: str | None
    content_type: str
    http_status: int | None
    discovery_depth: int | None
    checksum: str | None
    fetched_at: datetime
    created_at: datetime
    updated_at: datetime

    model_config = ConfigDict(from_attributes=True)


class CapturedResourceListResponse(BaseModel):
    data: list[CapturedResourceResponse]
    total: int
    limit: int
    offset: int


class RawArtifactResponse(BaseModel):
    artifact_id: str
    run_id: str
    source_id: str
    source_version_id: str
    storage_path: str
    content_type: str
    artifact_metadata: dict[str, Any]
    created_at: datetime
    updated_at: datetime

    model_config = ConfigDict(from_attributes=True)


class RawArtifactListResponse(BaseModel):
    data: list[RawArtifactResponse]
    total: int
    limit: int
    offset: int


class ProviderJobResponse(BaseModel):
    provider_job_id: str
    run_id: str
    provider: str
    external_job_id: str | None
    status: ProviderJobStatus
    last_event_type: str | None
    request_payload: dict[str, Any]
    response_payload: dict[str, Any]
    created_at: datetime
    updated_at: datetime

    model_config = ConfigDict(from_attributes=True)


class ProviderJobListResponse(BaseModel):
    data: list[ProviderJobResponse]
    total: int
    limit: int
    offset: int


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


class RunPipelineHealthStage(BaseModel):
    stage: str
    status: str
    detail: str
    updated_at: datetime | None


class RunPipelineHealthResponse(BaseModel):
    run_id: str
    source_id: str
    source_version_id: str
    mode: RunMode
    run_status: RunStatus
    overall_status: str
    stages: list[RunPipelineHealthStage]
    processing_status_event_count: int
    document_lifecycle_event_count: int
