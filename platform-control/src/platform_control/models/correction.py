from __future__ import annotations

from datetime import datetime
from typing import Any

from sqlalchemy import JSON, DateTime, Enum, Index
from sqlalchemy.orm import Mapped, mapped_column

from platform_control.domain import (
    CorrectionStatus,
    CorrectionTargetEntityType,
    CorrectionType,
)
from platform_control.ids import generate_prefixed_id
from platform_control.models.base import Base, TimestampMixin


class Correction(TimestampMixin, Base):
    """An operator-initiated correction recorded against a downstream entity.

    Corrections are append-only: each operator action that mutates, annotates,
    rejects, or asks for a rescore of a downstream artefact (currently only
    :class:`CommentaryInsight` overlays) lands as a row here. The overlay
    table is the read-model; this table is the audit log + work queue.

    Indexed on ``(target_entity_type, target_entity_id, created_at)`` so the
    per-entity history endpoint is cheap, and on ``(status, created_at)`` so
    the operator queue can scan pending work in arrival order.
    """

    __tablename__ = "corrections"
    __table_args__ = (
        Index(
            "ix_corrections_target_history",
            "target_entity_type",
            "target_entity_id",
            "created_at",
        ),
        Index(
            "ix_corrections_queue",
            "status",
            "created_at",
        ),
    )

    correction_id: Mapped[str] = mapped_column(
        primary_key=True, default=lambda: generate_prefixed_id("cor")
    )
    target_entity_type: Mapped[CorrectionTargetEntityType] = mapped_column(
        Enum(
            CorrectionTargetEntityType,
            native_enum=False,
            values_callable=lambda enum_cls: [member.value for member in enum_cls],
        ),
        nullable=False,
    )
    target_entity_id: Mapped[str] = mapped_column(nullable=False)
    correction_type: Mapped[CorrectionType] = mapped_column(
        Enum(
            CorrectionType,
            native_enum=False,
            values_callable=lambda enum_cls: [member.value for member in enum_cls],
        ),
        nullable=False,
    )
    # Free-form payload — shape depends on ``correction_type``. For
    # ``field_edit`` it's the patch dict; for ``annotation`` it carries the
    # note; for ``reject`` it carries the reason; for ``rescore_request`` it
    # may be empty. Storage uses ``JSON`` so the SQLite-backed test suite
    # works; on Postgres SQLAlchemy emits JSONB-compatible behaviour via the
    # generic JSON type — the migration can pin to ``JSONB`` for production.
    payload: Mapped[dict[str, Any]] = mapped_column(JSON, default=dict, nullable=False)
    # Snapshot of the target entity's relevant fields at the time the
    # correction was applied, used for optimistic concurrency on field_edit
    # and to make the audit log self-contained for rollback.
    original_snapshot: Mapped[dict[str, Any]] = mapped_column(JSON, default=dict, nullable=False)
    # ``operator_id`` is nullable because system-emitted ``rescore_request``
    # rows (#427) carry no operator — the row is created by the platform in
    # response to a parent operator correction.
    operator_id: Mapped[str | None] = mapped_column(nullable=True)
    pipeline_run_id: Mapped[str | None] = mapped_column(nullable=True)
    rationale: Mapped[str | None] = mapped_column(nullable=True)
    status: Mapped[CorrectionStatus] = mapped_column(
        Enum(
            CorrectionStatus,
            native_enum=False,
            values_callable=lambda enum_cls: [member.value for member in enum_cls],
        ),
        default=CorrectionStatus.PENDING,
        server_default=CorrectionStatus.PENDING.value,
        nullable=False,
    )
    # Rescore-loop columns (#427). For ``rescore_request`` rows these capture
    # the Temporal workflow handle and the eventual extraction outcome. They
    # remain NULL on operator corrections (``field_edit`` / ``annotation`` /
    # ``reject``).
    source_correction_id: Mapped[str | None] = mapped_column(nullable=True)
    workflow_id: Mapped[str | None] = mapped_column(nullable=True)
    workflow_run_id: Mapped[str | None] = mapped_column(nullable=True)
    resulting_run_id: Mapped[str | None] = mapped_column(nullable=True)
    resulting_extraction_id: Mapped[str | None] = mapped_column(nullable=True)
    completed_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True), nullable=True)
    applied_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True), nullable=True)
