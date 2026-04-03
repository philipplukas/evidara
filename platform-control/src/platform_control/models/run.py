from __future__ import annotations

from datetime import datetime

from sqlalchemy import JSON, DateTime, Enum, ForeignKey
from sqlalchemy.orm import Mapped, mapped_column, relationship

from platform_control.domain import RunMode, RunStatus
from platform_control.ids import generate_prefixed_id
from platform_control.models.base import Base, TimestampMixin, utcnow


class Run(TimestampMixin, Base):
    __tablename__ = "runs"

    run_id: Mapped[str] = mapped_column(
        primary_key=True,
        default=lambda: generate_prefixed_id("run"),
    )
    source_id: Mapped[str] = mapped_column(ForeignKey("sources.source_id"))
    source_version_id: Mapped[str] = mapped_column(ForeignKey("source_versions.source_version_id"))
    mode: Mapped[RunMode] = mapped_column(Enum(RunMode, native_enum=False), default=RunMode.PREVIEW)
    status: Mapped[RunStatus] = mapped_column(
        Enum(RunStatus, native_enum=False), default=RunStatus.PENDING
    )
    started_at: Mapped[datetime | None] = mapped_column(
        DateTime(timezone=True),
        nullable=True,
        default=utcnow,
    )
    completed_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True), nullable=True)
    artifacts_count: Mapped[int] = mapped_column(default=0)
    captured_resources_count: Mapped[int] = mapped_column(default=0)
    failure_reason: Mapped[str | None] = mapped_column(nullable=True)
    run_metadata: Mapped[dict] = mapped_column("metadata", JSON, default=dict)

    source = relationship("Source", back_populates="runs")
    source_version = relationship("SourceVersion", back_populates="runs")
    provider_jobs = relationship("ProviderJob", back_populates="run")

    @property
    def scope(self) -> dict:
        return dict((self.run_metadata or {}).get("scope") or {"kind": "full_source"})

    @property
    def replay(self) -> dict | None:
        replay = (self.run_metadata or {}).get("replay")
        return dict(replay) if isinstance(replay, dict) else None
