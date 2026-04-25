"""Pydantic schemas for the commentary-insight overlay surface.

Mirrors `contracts/schemas/commentary-insight.schema.json` (PR #434)
plus a thin overlay layer (`overlay_revision`, `last_correction_id`).
"""

from __future__ import annotations

from datetime import datetime
from typing import Any, Literal

from pydantic import BaseModel, ConfigDict, Field

_INSIGHT_ID_RE = r"^ins_[0-9a-hjkmnp-tv-z]{26}$"
_DOCUMENT_ID_RE = r"^doc_[0-9a-hjkmnp-tv-z]{26}$"
_PROCESSING_MANIFEST_ID_RE = r"^pm_[0-9a-hjkmnp-tv-z]{26}$"
_CORRECTION_ID_RE = r"^cor_[a-z0-9]+$"


class CommentaryInsightResponse(BaseModel):
    insight_id: str = Field(pattern=_INSIGHT_ID_RE)
    document_id: str = Field(pattern=_DOCUMENT_ID_RE)
    document_revision: int = Field(ge=1)
    processing_manifest_id: str = Field(pattern=_PROCESSING_MANIFEST_ID_RE)
    section_id: str | None
    citation_id: str | None
    record_kind: Literal["commentary_insight"] = "commentary_insight"
    insight_type: str
    claim: str
    display_text: str
    support: list[dict[str, Any]]
    referenced_authorities: list[dict[str, Any]]
    language: str | None
    jurisdiction_id: str | None
    jurisdiction_ids: list[str]
    authority_ids: list[str]
    source_document_ids: list[str]
    confidence: float = Field(ge=0.0, le=1.0)
    review_state: str
    generator: dict[str, Any]
    scores: dict[str, Any]
    # Wire field is `metadata` (matches contracts/schemas/commentary-insight),
    # but the SQLAlchemy attribute is `metadata_json` (the model class can't
    # use `metadata` — that name is reserved by SQLAlchemy's DeclarativeBase).
    # `validation_alias` reads from the model attribute; `serialization_alias`
    # keeps the wire name unchanged.
    metadata: dict[str, Any] | None = Field(
        default=None,
        validation_alias="metadata_json",
        serialization_alias="metadata",
    )
    overlay_revision: int = Field(ge=1)
    last_correction_id: str | None = Field(default=None, pattern=_CORRECTION_ID_RE)
    created_at: datetime
    updated_at: datetime

    model_config = ConfigDict(
        from_attributes=True,
        populate_by_name=True,
    )


class CommentaryInsightListResponse(BaseModel):
    data: list[CommentaryInsightResponse]
    total: int | None = None
    limit: int | None = None
    offset: int | None = None


class CommentaryInsightHistoryEntry(BaseModel):
    """One correction in the history of a commentary insight.

    Lighter than `CorrectionResponse` — drops the bidirectional fields
    (target_entity_*) since the history is scoped to a known insight.
    """

    correction_id: str = Field(pattern=_CORRECTION_ID_RE)
    correction_type: str
    payload: dict[str, Any]
    original_snapshot: dict[str, Any] | None
    operator_id: str
    pipeline_run_id: str | None
    rationale: str | None
    status: str
    created_at: datetime
    applied_at: datetime | None

    model_config = ConfigDict(from_attributes=True)


class CommentaryInsightHistoryResponse(BaseModel):
    insight_id: str = Field(pattern=_INSIGHT_ID_RE)
    overlay_revision: int = Field(ge=1)
    history: list[CommentaryInsightHistoryEntry]
