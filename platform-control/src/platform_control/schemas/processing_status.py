from __future__ import annotations

from datetime import datetime
from typing import Literal

from pydantic import BaseModel, ConfigDict, Field, model_validator

from platform_control.domain import ProcessingStatus


class ProcessingStatusProvenance(BaseModel):
    tenant_id: str = Field(pattern=r"^tenant_[a-z0-9_]+$")
    corpus_id: str = Field(pattern=r"^corpus_[a-z0-9_]+$")
    scope_type: Literal["global_public", "tenant_private", "tenant_shared"]
    source_id: str = Field(pattern=r"^src_[0-9a-hjkmnp-tv-z]{26}$")
    source_version_id: str = Field(pattern=r"^sv_[0-9a-hjkmnp-tv-z]{26}$")
    run_id: str = Field(pattern=r"^run_[0-9a-hjkmnp-tv-z]{26}$")
    source_snapshot_id: str | None = Field(default=None, pattern=r"^snap_[0-9a-hjkmnp-tv-z]{26}$")
    bundle_manifest_id: str | None = Field(default=None, pattern=r"^abm_[0-9a-hjkmnp-tv-z]{26}$")
    artifact_id: str | None = Field(default=None, pattern=r"^art_[0-9a-hjkmnp-tv-z]{26}$")
    document_id: str | None = Field(default=None, pattern=r"^doc_[0-9a-hjkmnp-tv-z]{26}$")
    document_revision: int | None = Field(default=None, ge=1)
    processing_manifest_id: str | None = Field(default=None, pattern=r"^pm_[0-9a-hjkmnp-tv-z]{26}$")

    model_config = ConfigDict(extra="forbid")


class ProcessingStatusPayload(BaseModel):
    processing_manifest_id: str = Field(pattern=r"^pm_[0-9a-hjkmnp-tv-z]{26}$")
    document_id: str | None = Field(default=None, pattern=r"^doc_[0-9a-hjkmnp-tv-z]{26}$")
    document_revision: int | None = Field(default=None, ge=1)
    provenance: ProcessingStatusProvenance
    processing_version: str
    status: ProcessingStatus
    error_code: str | None = None
    error_summary: str | None = None

    @model_validator(mode="after")
    def validate_failure_fields(self) -> ProcessingStatusPayload:
        if self.status is ProcessingStatus.FAILED:
            if not self.error_code or not self.error_summary:
                raise ValueError("failed status requires non-empty error_code and error_summary")
        elif self.error_code is not None or self.error_summary is not None:
            raise ValueError("error_code and error_summary must be null unless status is failed")
        return self

    model_config = ConfigDict(extra="forbid")


class DocumentProcessingStatusUpdatedEvent(BaseModel):
    event_type: Literal["document.processing_status.updated"]
    event_version: Literal[1]
    event_id: str
    occurred_at: datetime
    producer: Literal["document-intelligence"]
    correlation_id: str | None = Field(default=None, pattern=r"^run_[0-9a-hjkmnp-tv-z]{26}$")
    causation_id: str | None = None
    payload: ProcessingStatusPayload

    model_config = ConfigDict(extra="forbid")


class ProcessingStatusUpdateResponse(BaseModel):
    event_id: str
    processing_manifest_id: str
    processing_version: str
    status: ProcessingStatus
    occurred_at: datetime
    source_snapshot_id: str | None
    bundle_manifest_id: str | None
    document_id: str | None
    document_revision: int | None
    error_code: str | None
    error_summary: str | None
    created_at: datetime
    updated_at: datetime

    model_config = ConfigDict(from_attributes=True)


class ProcessingStatusUpdateListResponse(BaseModel):
    data: list[ProcessingStatusUpdateResponse]


class EventAcceptedResponse(BaseModel):
    status: Literal["accepted"] = "accepted"
