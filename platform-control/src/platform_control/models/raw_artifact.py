from __future__ import annotations

from sqlalchemy import JSON, ForeignKey
from sqlalchemy.orm import Mapped, mapped_column

from platform_control.ids import generate_prefixed_id
from platform_control.models.base import Base, TimestampMixin


class RawArtifact(TimestampMixin, Base):
    __tablename__ = "raw_artifacts"

    artifact_id: Mapped[str] = mapped_column(
        primary_key=True,
        default=lambda: generate_prefixed_id("art"),
    )
    run_id: Mapped[str] = mapped_column(ForeignKey("runs.run_id"))
    source_id: Mapped[str] = mapped_column(ForeignKey("sources.source_id"))
    source_version_id: Mapped[str] = mapped_column(ForeignKey("source_versions.source_version_id"))
    storage_path: Mapped[str] = mapped_column()
    content_type: Mapped[str] = mapped_column()
    artifact_metadata: Mapped[dict] = mapped_column("metadata", JSON, default=dict)
