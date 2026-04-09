from __future__ import annotations

from datetime import datetime

from sqlalchemy import JSON, DateTime, Enum, ForeignKey
from sqlalchemy.orm import Mapped, mapped_column, relationship

from platform_control.domain import ReviewTaskStatus
from platform_control.ids import generate_prefixed_id
from platform_control.models.base import Base, TimestampMixin


class ReviewTask(TimestampMixin, Base):
    __tablename__ = "review_tasks"

    review_task_id: Mapped[str] = mapped_column(
        primary_key=True,
        default=lambda: generate_prefixed_id("wrt"),
    )
    wizard_run_id: Mapped[str] = mapped_column(
        ForeignKey("wizard_runs.wizard_run_id"),
        nullable=False,
    )
    argilla_external_id: Mapped[str] = mapped_column(nullable=False, unique=True)
    record_id: Mapped[str | None] = mapped_column(nullable=True)
    status: Mapped[ReviewTaskStatus] = mapped_column(
        Enum(
            ReviewTaskStatus,
            native_enum=False,
            values_callable=lambda enum_cls: [member.value for member in enum_cls],
        ),
        default=ReviewTaskStatus.PENDING,
    )
    payload: Mapped[dict] = mapped_column(JSON, default=dict)
    decision_payload: Mapped[dict | None] = mapped_column(JSON, nullable=True)
    processed_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True), nullable=True)
    argilla_enqueued_at: Mapped[datetime | None] = mapped_column(
        DateTime(timezone=True), nullable=True
    )
    argilla_enqueue_last_error: Mapped[str | None] = mapped_column(nullable=True)

    wizard_run = relationship("WizardRun", back_populates="review_tasks")
