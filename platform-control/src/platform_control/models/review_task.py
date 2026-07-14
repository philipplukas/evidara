"""Operator review queue for low-confidence / conflicting extractions.

A ``ReviewTask`` is one extraction an operator must look at before it is accepted.
What lands here is decided by the **confidence-band routing policy**, which is
retained and is independent of any particular review tool (ADR-0031):

- ``>= 0.90`` — auto-accept, with a 5% audit sample routed to review
- ``0.70 – 0.90`` — sampled: at least 20% routed to review
- ``< 0.70`` — mandatory review
- any extractor conflict — mandatory review, whatever the confidence

The bands and the operator flow live in ``docs/runbooks/extraction-review-routing.md``.

The review *surface* is ``platform-control/admin``. Tasks were once also pushed to a
hosted Argilla instance; that integration is gone (ADR-0031, #563), and a task's
decision now arrives through ``POST /v1/reviews/tasks/{task_id}/decision``.
"""

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
    # Stable key supplied by whatever produced the task (the extraction pipeline).
    # Unique, so re-routing the same record conflicts instead of double-queueing.
    # Formerly `argilla_external_id`: the dedupe key outlived Argilla, the name did not.
    external_id: Mapped[str] = mapped_column(nullable=False, unique=True)
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

    wizard_run = relationship("WizardRun", back_populates="review_tasks")
