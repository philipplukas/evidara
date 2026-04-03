from __future__ import annotations

from datetime import datetime

from pydantic import BaseModel, ConfigDict, Field, HttpUrl, model_validator

from platform_control.domain import RunMode, RunReplayMode, RunScopeKind, RunStatus


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
    run_id: str
    source_id: str
    source_version_id: str
    mode: RunMode
    scope: RunScopeRequest
    replay: RunReplayRequest | None
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
