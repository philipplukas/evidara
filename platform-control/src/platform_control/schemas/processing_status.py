from __future__ import annotations

from datetime import datetime
from typing import Literal

from pydantic import BaseModel, ConfigDict, model_validator

from platform_control.domain import ProcessingStatus


class ProcessingStatusProvenance(BaseModel):
    tenant_id: str
    corpus_id: str
    scope_type: str
    source_id: str
    source_version_id: str
    run_id: str
    source_snapshot_id: str | None = None
    bundle_manifest_id: str | None = None
    artifact_id: str | None = None
    document_id: str | None = None
    document_revision: int | None = None
    processing_manifest_id: str | None = None

    model_config = ConfigDict(extra="forbid")


class ProcessingStatusPayload(BaseModel):
    processing_manifest_id: str
    document_id: str | None = None
    document_revision: int | None = None
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
    correlation_id: str | None = None
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
