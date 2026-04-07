from __future__ import annotations

from sqlalchemy import JSON, Enum
from sqlalchemy.orm import Mapped, mapped_column, relationship

from platform_control.domain import WizardProjectStatus
from platform_control.ids import generate_prefixed_id
from platform_control.models.base import Base, TimestampMixin


class WizardProject(TimestampMixin, Base):
    __tablename__ = "wizard_projects"

    wizard_project_id: Mapped[str] = mapped_column(
        primary_key=True,
        default=lambda: generate_prefixed_id("wpr"),
    )
    name: Mapped[str] = mapped_column(nullable=False)
    status: Mapped[WizardProjectStatus] = mapped_column(
        Enum(WizardProjectStatus, native_enum=False),
        default=WizardProjectStatus.DRAFT,
    )
    scope: Mapped[dict] = mapped_column(JSON, default=dict)
    discovery_plan: Mapped[dict] = mapped_column(JSON, default=dict)

    wizard_runs = relationship("WizardRun", back_populates="wizard_project")
