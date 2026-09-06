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


class PipelineStage(BaseModel):
    """One document-intelligence stage's timing and counts.

    Mirrors `contracts/events/document-processed.schema.json#/…/stages/items`.
    Timings and counts ONLY: this does NOT say what the stage removed from the
    text (footnote apparatus, page furniture, a lifted Randtitel, a dropped
    citation) — that disclosure is ADR-0044's subject and is not implemented.

    `items_in` / `items_out` are `None` when the stage did not measure them, and
    a renderer must show that as "not recorded" rather than as `0`: absence and
    zero are different facts, and only one of them is a claim about the work.
    """

    name: Literal["normalize", "sectionize", "extract", "assemble", "enrich", "finalize"]
    #: MICROSECONDS. Measured 2026-09-06, every stage of a small HTML document
    #: reported `0 ms` — truthful and useless, because a reader cannot tell
    #: "fast" from "not measured". Milliseconds cannot express this pipeline's
    #: own timings, so the unit is microseconds and clients format for display.
    duration_us: int = Field(ge=0)
    items_in: int | None = Field(default=None, ge=0)
    items_out: int | None = Field(default=None, ge=0)
    failed: bool = False
    error_type: str | None = None
    #: Reserved for ADR-0044. Absent today; absence means "not recorded", never
    #: "nothing was removed".
    details: dict[str, Any] | None = None

    model_config = ConfigDict(extra="forbid")


class DocumentProcessedPayload(BaseModel):
    document_id: str = Field(pattern=r"^doc_[0-9a-hjkmnp-tv-z]{26}$")
    document_revision: int = Field(ge=1)
    processing_manifest_id: str = Field(pattern=r"^pm_[0-9a-hjkmnp-tv-z]{26}$")
    processing_version: str
    provenance: ProcessingStatusProvenance
    authority_id: str | None = Field(default=None, pattern=r"^auth_[a-z0-9_]+$")
    authority_name: str | None = None
    is_official: bool = False
    lifecycle_status: DocumentLifecycleStatus
    published_document_ref: DatasetRef
    published_sections_ref: DatasetRef
    processing_manifest_ref: ManifestRef
    supersedes_processing_manifest_id: str | None = Field(
        default=None,
        pattern=r"^pm_[0-9a-hjkmnp-tv-z]{26}$",
    )
    #: Defaults to an EMPTY list, and that default means "the producer sent no
    #: ledger" — an older document-intelligence, or a path that builds no
    #: ledger. It does not mean the pipeline ran no stages, and no surface may
    #: render it as though it did.
    stages: list[PipelineStage] = Field(default_factory=list)

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
    #: `null` means document-intelligence recorded no stage ledger for this
    #: document — an event from before #905, or a producer that emits none. It
    #: does NOT mean the pipeline ran no stages, and a client must render it as
    #: "not recorded" rather than as an empty or zeroed timeline.
    stages: list[PipelineStage] | None = None
    occurred_at: datetime
    created_at: datetime
    updated_at: datetime

    model_config = ConfigDict(from_attributes=True)


class DocumentLifecycleEventListResponse(BaseModel):
    data: list[DocumentLifecycleEventResponse]
