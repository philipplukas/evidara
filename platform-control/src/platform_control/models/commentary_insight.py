from __future__ import annotations

from typing import Any

from sqlalchemy import JSON
from sqlalchemy.orm import Mapped, mapped_column

from platform_control.models.base import Base, TimestampMixin


class CommentaryInsight(TimestampMixin, Base):
    """Operator-facing commentary insight overlay.

    Mirrors `contracts/schemas/commentary-insight.schema.json` plus an
    overlay layer (`overlay_revision`, `last_correction_id`) that lets
    the platform-control API surface "current state after applied
    corrections" without joining against the corrections audit log on
    every read.

    Populated by document-intelligence runs (initial revision = 1) and
    amended by `CorrectionService.apply` whenever a correction targeting
    `target_entity_type == 'commentary_insight'` transitions to
    `applied`.
    """

    __tablename__ = "commentary_insights"

    insight_id: Mapped[str] = mapped_column(primary_key=True)
    document_id: Mapped[str] = mapped_column(nullable=False)
    document_revision: Mapped[int] = mapped_column(nullable=False)
    processing_manifest_id: Mapped[str] = mapped_column(nullable=False)
    section_id: Mapped[str | None] = mapped_column(nullable=True)
    citation_id: Mapped[str | None] = mapped_column(nullable=True)
    insight_type: Mapped[str] = mapped_column(nullable=False)
    claim: Mapped[str] = mapped_column(nullable=False)
    display_text: Mapped[str] = mapped_column(nullable=False)
    language: Mapped[str | None] = mapped_column(nullable=True)
    jurisdiction_id: Mapped[str | None] = mapped_column(nullable=True)
    confidence: Mapped[float] = mapped_column(nullable=False)
    review_state: Mapped[str] = mapped_column(nullable=False)
    support: Mapped[list[dict[str, Any]]] = mapped_column(JSON, nullable=False)
    referenced_authorities: Mapped[list[dict[str, Any]]] = mapped_column(JSON, nullable=False)
    jurisdiction_ids: Mapped[list[str]] = mapped_column(JSON, nullable=False)
    authority_ids: Mapped[list[str]] = mapped_column(JSON, nullable=False)
    source_document_ids: Mapped[list[str]] = mapped_column(JSON, nullable=False)
    generator: Mapped[dict[str, Any]] = mapped_column(JSON, nullable=False)
    scores: Mapped[dict[str, Any]] = mapped_column(JSON, nullable=False)
    metadata_json: Mapped[dict[str, Any] | None] = mapped_column(JSON, nullable=True)
    overlay_revision: Mapped[int] = mapped_column(nullable=False, default=1)
    last_correction_id: Mapped[str | None] = mapped_column(nullable=True)
