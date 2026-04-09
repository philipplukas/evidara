from __future__ import annotations

from datetime import datetime

from sqlalchemy import JSON, DateTime, Enum, ForeignKey
from sqlalchemy.orm import Mapped, mapped_column, relationship

from platform_control.domain import WizardRunState
from platform_control.ids import generate_prefixed_id
from platform_control.models.base import Base, TimestampMixin, utcnow


class WizardRun(TimestampMixin, Base):
    __tablename__ = "wizard_runs"

    wizard_run_id: Mapped[str] = mapped_column(
        primary_key=True,
        default=lambda: generate_prefixed_id("wrn"),
    )
    wizard_project_id: Mapped[str] = mapped_column(
        ForeignKey("wizard_projects.wizard_project_id"),
        nullable=False,
    )
    workflow_id: Mapped[str | None] = mapped_column(nullable=True)
    state: Mapped[WizardRunState] = mapped_column(
        Enum(
            WizardRunState,
            native_enum=False,
            values_callable=lambda enum_cls: [member.value for member in enum_cls],
        ),
        default=WizardRunState.DRAFT_SCOPE,
    )
    state_entered_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True),
        default=utcnow,
    )
    progress: Mapped[dict] = mapped_column(JSON, default=dict)
    quality: Mapped[dict] = mapped_column(JSON, default=dict)
    health: Mapped[dict] = mapped_column(JSON, default=dict)
    failure_reason: Mapped[str | None] = mapped_column(nullable=True)

    wizard_project = relationship("WizardProject", back_populates="wizard_runs")
    review_tasks = relationship("ReviewTask", back_populates="wizard_run")
    ledger = relationship("WizardRunLedger", back_populates="wizard_run", uselist=False)
