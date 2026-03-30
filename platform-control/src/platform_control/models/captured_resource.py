from __future__ import annotations

from datetime import datetime

from sqlalchemy import JSON, ForeignKey
from sqlalchemy.orm import Mapped, mapped_column

from platform_control.ids import generate_prefixed_id
from platform_control.models.base import Base, TimestampMixin, utcnow


class CapturedResource(TimestampMixin, Base):
    __tablename__ = "captured_resources"

    captured_resource_id: Mapped[str] = mapped_column(
        primary_key=True, default=lambda: generate_prefixed_id("cap")
    )
    artifact_id: Mapped[str] = mapped_column(ForeignKey("raw_artifacts.artifact_id"))
    run_id: Mapped[str] = mapped_column(ForeignKey("runs.run_id"))
    source_id: Mapped[str] = mapped_column(ForeignKey("sources.source_id"))
    source_version_id: Mapped[str] = mapped_column(ForeignKey("source_versions.source_version_id"))
    provider_job_id: Mapped[str | None] = mapped_column(
        ForeignKey("provider_jobs.provider_job_id"), nullable=True
    )
    provider: Mapped[str] = mapped_column(default="firecrawl")
    source_url: Mapped[str] = mapped_column()
    final_url: Mapped[str] = mapped_column()
    title: Mapped[str | None] = mapped_column(nullable=True)
    content_type: Mapped[str] = mapped_column()
    checksum: Mapped[str | None] = mapped_column(nullable=True)
    http_status: Mapped[int | None] = mapped_column(nullable=True)
    discovery_depth: Mapped[int | None] = mapped_column(nullable=True)
    fetched_at: Mapped[datetime] = mapped_column(default=utcnow)
    resource_metadata: Mapped[dict] = mapped_column("metadata", JSON, default=dict)
