from __future__ import annotations

from datetime import datetime
from typing import Any

from sqlalchemy import JSON, DateTime, Enum, ForeignKey, Index
from sqlalchemy.orm import Mapped, mapped_column

from platform_control.domain import CommentaryInsightReviewState
from platform_control.models.base import Base, TimestampMixin, utcnow


class CommentaryInsight(TimestampMixin, Base):
    """Operator-editable overlay for a commentary insight.

    The canonical record is produced by document-intelligence; this row is the
    platform-control read-model that operators can patch through the admin UI.
    Each patch lands as a :class:`Correction` row and updates the matching
    fields here, bumping ``current_version`` and pointing
    ``last_correction_id`` at the most recent correction so the history endpoint
    can hop straight back into the audit log.

    Field shapes match ``contracts/schemas/commentary-insight.schema.json``.
    JSON-typed columns hold the array/object subfields verbatim so we don't
    need a follow-up migration each time the contract grows a new property.
    """

    __tablename__ = "commentary_insights"
    __table_args__ = (
        Index("ix_commentary_insights_document", "document_id"),
        Index("ix_commentary_insights_jurisdiction", "jurisdiction_id"),
        # CONTRACT-PENDING #423: authority_id is not in the v1 schema yet but
        # the issue calls for filtering by authority — kept as a reserved
        # column so the index can land without a follow-up migration when the
        # contract freezes.
        Index("ix_commentary_insights_authority", "authority_id"),
    )

    # Use the contract's ``insight_id`` as the primary key directly so the
    # overlay is addressable by the same handle as the canonical record.
    insight_id: Mapped[str] = mapped_column(primary_key=True)
    document_id: Mapped[str] = mapped_column(nullable=False)
    document_revision: Mapped[int] = mapped_column(nullable=False)
    processing_manifest_id: Mapped[str] = mapped_column(nullable=False)
    section_id: Mapped[str | None] = mapped_column(nullable=True)
    citation_id: Mapped[str | None] = mapped_column(nullable=True)
    insight_type: Mapped[str] = mapped_column(nullable=False)
    claim: Mapped[str] = mapped_column(nullable=False)
    display_text: Mapped[str] = mapped_column(nullable=False)
    support: Mapped[list[dict[str, Any]]] = mapped_column(JSON, default=list, nullable=False)
    referenced_authorities: Mapped[list[dict[str, Any]]] = mapped_column(
        JSON, default=list, nullable=False
    )
    language: Mapped[str | None] = mapped_column(nullable=True)
    jurisdiction_id: Mapped[str | None] = mapped_column(nullable=True)
    # CONTRACT-PENDING #423: authority_id is not (yet) in the schema. Issue
    # body calls for authority filtering on the list endpoint, so we reserve
    # the column. Remove if the freeze does not include it.
    authority_id: Mapped[str | None] = mapped_column(nullable=True)
    # CONTRACT-PENDING #423: source_document_id is also called out by the
    # issue but the schema only has ``document_id``. We treat source_document_id
    # filters as aliases for document_id at the API layer.
    confidence: Mapped[float] = mapped_column(nullable=False)
    review_state: Mapped[CommentaryInsightReviewState] = mapped_column(
        Enum(
            CommentaryInsightReviewState,
            native_enum=False,
            values_callable=lambda enum_cls: [member.value for member in enum_cls],
        ),
        nullable=False,
    )
    generator: Mapped[dict[str, Any]] = mapped_column(JSON, default=dict, nullable=False)
    scores: Mapped[dict[str, Any]] = mapped_column(JSON, default=dict, nullable=False)
    extra_metadata: Mapped[dict[str, Any] | None] = mapped_column("metadata", JSON, nullable=True)

    current_version: Mapped[int] = mapped_column(default=1, server_default="1", nullable=False)
    last_correction_id: Mapped[str | None] = mapped_column(
        ForeignKey("corrections.correction_id"), nullable=True
    )
    overlay_updated_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), default=utcnow, nullable=False
    )
