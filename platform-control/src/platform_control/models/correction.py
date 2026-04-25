from __future__ import annotations

from datetime import datetime
from typing import Any

from sqlalchemy import JSON, DateTime
from sqlalchemy.orm import Mapped, mapped_column

from platform_control.ids import generate_prefixed_id
from platform_control.models.base import Base


class Correction(Base):
    """HITL correction raised against an upstream domain entity.

    Mirrors the wire shape frozen in `contracts/schemas/corrections.json`
    (PR #434). Acts as the durable audit log for every operator-raised or
    pipeline-raised correction; downstream projections (search, admin
    overlays) rebuild from upstream entities and reference this row only
    via `last_correction_id` hints, never via FK.

    State machine (enforced server-side in CorrectionService, not as DB
    constraints — keeps the audit log additive even on illegal
    transition attempts):

        pending  ──→ applied  ──→ superseded
            └──→ rejected
    """

    __tablename__ = "corrections"

    correction_id: Mapped[str] = mapped_column(
        primary_key=True, default=lambda: generate_prefixed_id("cor")
    )
    target_entity_type: Mapped[str] = mapped_column(nullable=False)
    target_entity_id: Mapped[str] = mapped_column(nullable=False)
    correction_type: Mapped[str] = mapped_column(nullable=False)
    payload: Mapped[dict[str, Any]] = mapped_column(JSON, nullable=False)
    original_snapshot: Mapped[dict[str, Any] | None] = mapped_column(JSON, nullable=True)
    operator_id: Mapped[str] = mapped_column(nullable=False)
    pipeline_run_id: Mapped[str | None] = mapped_column(nullable=True)
    rationale: Mapped[str | None] = mapped_column(nullable=True)
    status: Mapped[str] = mapped_column(nullable=False, default="pending")
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), nullable=False)
    applied_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True), nullable=True)
