from __future__ import annotations

from datetime import datetime

from sqlalchemy import Boolean, DateTime, String, UniqueConstraint
from sqlalchemy.orm import Mapped, mapped_column

from platform_control.ids import generate_prefixed_id
from platform_control.models.base import Base, utcnow


class BlueprintTemplateOverride(Base):
    """Operator-owned enablement state for a source blueprint template (#632).

    Config-owner key of the ADR-0030 two-key lock. The *shipped default* lives
    in ``source_blueprints.yaml`` (fail-closed: a template with no ``enabled:
    true`` is inert). That file is code — an operator cannot flip it without a
    PR and a deploy, which breaks the #628 thesis that a new source costs an
    *operator*, not an *engineer*.

    This table is the operator-reachable half. A row's presence overrides the
    YAML default for one ``(overlay_id, provider_template_id)`` pair; its absence
    means "use the shipped default". Flipping it is an API call an operator makes
    after capturing acceptance-run evidence — no repo edit, no release.

    ``updated_by``/``note``/``updated_at`` are the audit trail: who turned the
    key, when, and why. The *code-owner* key (``live_ready``) deliberately stays
    in code — it is an engineering assertion that the provider can physically
    acquire the format, not operational state.
    """

    __tablename__ = "blueprint_template_overrides"
    __table_args__ = (
        UniqueConstraint(
            "overlay_id",
            "provider_template_id",
            name="uq_blueprint_template_override_key",
        ),
    )

    override_id: Mapped[str] = mapped_column(
        String,
        primary_key=True,
        default=lambda: generate_prefixed_id("bto"),
    )
    overlay_id: Mapped[str] = mapped_column(String, nullable=False)
    provider_template_id: Mapped[str] = mapped_column(String, nullable=False)
    enabled: Mapped[bool] = mapped_column(Boolean, nullable=False)
    note: Mapped[str | None] = mapped_column(String, nullable=True)
    updated_by: Mapped[str | None] = mapped_column(String, nullable=True)
    created_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), nullable=False, default=utcnow
    )
    updated_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), nullable=False, default=utcnow, onupdate=utcnow
    )
