from __future__ import annotations

from datetime import datetime
from typing import Any, Literal

from pydantic import BaseModel, ConfigDict, Field

from platform_control.domain import (
    DocumentLifecycleStatus,
    DocumentWithdrawalReason,
    SearchDisposition,
)
from platform_control.schemas.processing_status import ProcessingStatusProvenance


class DatasetRef(BaseModel):
    surface_name: str
    surface_version: int = Field(ge=1)
    record_key: dict[str, Any] | None = None
    record_filter: dict[str, Any] | None = None

    model_config = ConfigDict(extra="forbid")


class ManifestRef(BaseModel):
    manifest_id: str
    manifest_type: str
    manifest_version: int = Field(ge=1)
    dataset_ref: DatasetRef

    model_config = ConfigDict(extra="forbid")


class DocumentProcessedPayload(BaseModel):
    document_id: str = Field(pattern=r"^doc_[0-9a-hjkmnp-tv-z]{26}$")
    document_revision: int = Field(ge=1)
    processing_manifest_id: str = Field(pattern=r"^pm_[0-9a-hjkmnp-tv-z]{26}$")
    processing_version: str
    provenance: ProcessingStatusProvenance
    lifecycle_status: DocumentLifecycleStatus
    published_document_ref: DatasetRef
    published_sections_ref: DatasetRef
    processing_manifest_ref: ManifestRef
    supersedes_processing_manifest_id: str | None = Field(
        default=None,
        pattern=r"^pm_[0-9a-hjkmnp-tv-z]{26}$",
    )

    model_config = ConfigDict(extra="forbid")


class DocumentProcessedEvent(BaseModel):
    event_type: Literal["document.processed"]
    event_version: Literal[1]
    event_id: str
    occurred_at: datetime
    producer: Literal["document-intelligence"]
    correlation_id: str | None = Field(default=None, pattern=r"^run_[0-9a-hjkmnp-tv-z]{26}$")
    causation_id: str | None = None
    payload: DocumentProcessedPayload

    model_config = ConfigDict(extra="forbid")


class DocumentWithdrawnPayload(BaseModel):
    document_id: str = Field(pattern=r"^doc_[0-9a-hjkmnp-tv-z]{26}$")
    document_revision: int = Field(ge=1)
    processing_manifest_id: str = Field(pattern=r"^pm_[0-9a-hjkmnp-tv-z]{26}$")
    provenance: ProcessingStatusProvenance
    reason_code: DocumentWithdrawalReason
    reason_summary: str | None = None
    search_disposition: SearchDisposition

    model_config = ConfigDict(extra="forbid")


class DocumentWithdrawnEvent(BaseModel):
    event_type: Literal["document.withdrawn"]
    event_version: Literal[1]
    event_id: str
    occurred_at: datetime
    producer: Literal["document-intelligence"]
    correlation_id: str | None = Field(default=None, pattern=r"^run_[0-9a-hjkmnp-tv-z]{26}$")
    causation_id: str | None = None
    payload: DocumentWithdrawnPayload

    model_config = ConfigDict(extra="forbid")


class DocumentLifecycleEventResponse(BaseModel):
    event_id: str
    event_type: str
    run_id: str
    document_id: str
    document_revision: int
    processing_manifest_id: str
    processing_version: str | None
    lifecycle_status: str | None
    reason_code: str | None
    reason_summary: str | None
    search_disposition: str | None
    occurred_at: datetime
    created_at: datetime
    updated_at: datetime

    model_config = ConfigDict(from_attributes=True)


class DocumentLifecycleEventListResponse(BaseModel):
    data: list[DocumentLifecycleEventResponse]
