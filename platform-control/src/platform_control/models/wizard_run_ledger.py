from __future__ import annotations

from sqlalchemy import JSON, ForeignKey
from sqlalchemy.orm import Mapped, mapped_column, relationship

from platform_control.ids import generate_prefixed_id
from platform_control.models.base import Base, TimestampMixin


class WizardRunLedger(TimestampMixin, Base):
    __tablename__ = "wizard_run_ledgers"

    wizard_run_ledger_id: Mapped[str] = mapped_column(
        primary_key=True,
        default=lambda: generate_prefixed_id("wrl"),
    )
    wizard_run_id: Mapped[str] = mapped_column(
        ForeignKey("wizard_runs.wizard_run_id"),
        nullable=False,
        unique=True,
    )
    state_transitions: Mapped[dict] = mapped_column(JSON, default=dict)
    retry_counters: Mapped[dict] = mapped_column(JSON, default=dict)
    error_summary: Mapped[dict] = mapped_column(JSON, default=dict)
    sla_markers: Mapped[dict] = mapped_column(JSON, default=dict)
    published_version: Mapped[str | None] = mapped_column(nullable=True)

    wizard_run = relationship("WizardRun", back_populates="ledger")
