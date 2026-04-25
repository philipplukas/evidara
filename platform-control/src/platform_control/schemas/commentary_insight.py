from __future__ import annotations

from datetime import datetime
from typing import Any

from pydantic import BaseModel, ConfigDict, Field, model_validator

from platform_control.domain import CommentaryInsightReviewState

# Fields that operators are allowed to overwrite via PATCH. Anything outside
# this set is treated as immutable provenance (document_id, processing_manifest_id,
# generator, scores, …) and rejected. Keep this list narrow; new editable fields
# should be opt-in.
EDITABLE_FIELDS = frozenset(
    {
        "claim",
        "display_text",
        "review_state",
        "referenced_authorities",
        "language",
        "jurisdiction_id",
        "authority_id",
        "metadata",
    }
)


class ReferencedAuthorityModel(BaseModel):
    """Mirror of the contract's ``referenced_authorities[]`` shape."""

    text: str = Field(min_length=1)
    citation_type: str = Field(min_length=1)
    normalized_reference: str | None = None
    metadata: dict[str, Any] | None = None

    model_config = ConfigDict(extra="forbid")


class CommentaryInsightResponse(BaseModel):
    """Read-model view of a commentary insight overlay row."""

    insight_id: str
    document_id: str
    document_revision: int
    processing_manifest_id: str
    section_id: str | None
    citation_id: str | None
    insight_type: str
    claim: str
    display_text: str
    support: list[dict[str, Any]]
    referenced_authorities: list[dict[str, Any]]
    language: str | None
    jurisdiction_id: str | None
    authority_id: str | None
    confidence: float
    review_state: CommentaryInsightReviewState
    generator: dict[str, Any]
    scores: dict[str, Any]
    metadata: dict[str, Any] | None = None

    current_version: int
    last_correction_id: str | None
    overlay_updated_at: datetime
    created_at: datetime
    updated_at: datetime

    model_config = ConfigDict(from_attributes=True)

    @classmethod
    def from_orm_row(cls, row: Any) -> CommentaryInsightResponse:
        """Adapter — the ORM uses ``extra_metadata`` because ``metadata`` clashes
        with SQLAlchemy's ``DeclarativeBase.metadata`` attribute."""
        payload = {
            "insight_id": row.insight_id,
            "document_id": row.document_id,
            "document_revision": row.document_revision,
            "processing_manifest_id": row.processing_manifest_id,
            "section_id": row.section_id,
            "citation_id": row.citation_id,
            "insight_type": row.insight_type,
            "claim": row.claim,
            "display_text": row.display_text,
            "support": row.support,
            "referenced_authorities": row.referenced_authorities,
            "language": row.language,
            "jurisdiction_id": row.jurisdiction_id,
            "authority_id": row.authority_id,
            "confidence": row.confidence,
            "review_state": row.review_state,
            "generator": row.generator,
            "scores": row.scores,
            "metadata": row.extra_metadata,
            "current_version": row.current_version,
            "last_correction_id": row.last_correction_id,
            "overlay_updated_at": row.overlay_updated_at,
            "created_at": row.created_at,
            "updated_at": row.updated_at,
        }
        return cls.model_validate(payload)


class CommentaryInsightListResponse(BaseModel):
    data: list[CommentaryInsightResponse]
    next_cursor: str | None = None


class CommentaryInsightListQuery(BaseModel):
    jurisdiction_id: str | None = None
    authority_id: str | None = None
    source_document_id: str | None = None
    review_state: CommentaryInsightReviewState | None = None
    limit: int = Field(default=50, ge=1, le=500)
    cursor: str | None = None


class PatchCommentaryInsightRequest(BaseModel):
    """Atomic operator patch.

    The patch is split into three pieces: the field updates (``patch``),
    the snapshot of the fields the operator believed they were editing
    (``original_snapshot``, used for optimistic concurrency), and the
    audit metadata (``operator_id``, ``rationale``, ``pipeline_run_id``).
    """

    operator_id: str = Field(min_length=1)
    rationale: str | None = None
    pipeline_run_id: str | None = None
    patch: dict[str, Any] = Field(default_factory=dict)
    original_snapshot: dict[str, Any] = Field(default_factory=dict)

    model_config = ConfigDict(extra="forbid")

    @model_validator(mode="after")
    def validate_patch(self) -> PatchCommentaryInsightRequest:
        if not self.patch:
            raise ValueError("patch must include at least one field to update.")
        unknown = set(self.patch) - EDITABLE_FIELDS
        if unknown:
            raise ValueError("Unsupported patch fields: " + ", ".join(sorted(unknown)))
        # Snapshot must cover every patched field so we can compare apples to
        # apples for optimistic concurrency. Otherwise a partial snapshot
        # would let stale writes slip through.
        missing_snapshot = set(self.patch) - set(self.original_snapshot)
        if missing_snapshot:
            raise ValueError(
                "original_snapshot must include all fields in patch; missing: "
                + ", ".join(sorted(missing_snapshot))
            )
        return self
