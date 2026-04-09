from __future__ import annotations

from datetime import datetime

from sqlalchemy import Boolean, DateTime, Enum, ForeignKey, String
from sqlalchemy.orm import Mapped, mapped_column, relationship

from platform_control.domain import RunMode
from platform_control.ids import generate_prefixed_id
from platform_control.models.base import Base, TimestampMixin


class Schedule(TimestampMixin, Base):
    __tablename__ = "schedules"

    schedule_id: Mapped[str] = mapped_column(
        primary_key=True,
        default=lambda: generate_prefixed_id("sched"),
    )
    source_id: Mapped[str] = mapped_column(ForeignKey("sources.source_id"))
    source_version_id: Mapped[str] = mapped_column(ForeignKey("source_versions.source_version_id"))
    cron_expression: Mapped[str] = mapped_column(String(128))
    timezone: Mapped[str] = mapped_column(String(64), default="UTC")
    mode: Mapped[RunMode] = mapped_column(
        Enum(
            RunMode,
            native_enum=False,
            values_callable=lambda enum_cls: [member.value for member in enum_cls],
        ),
        default=RunMode.PRODUCTION,
    )
    enabled: Mapped[bool] = mapped_column(Boolean, default=True)
    description: Mapped[str | None] = mapped_column(String(512), nullable=True)
    last_triggered_at: Mapped[datetime | None] = mapped_column(
        DateTime(timezone=True), nullable=True
    )
    last_run_id: Mapped[str | None] = mapped_column(nullable=True)

    source = relationship("Source")
    source_version = relationship("SourceVersion")
