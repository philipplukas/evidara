from __future__ import annotations

from sqlalchemy import JSON, Enum, ForeignKey
from sqlalchemy.orm import Mapped, mapped_column, relationship

from platform_control.domain import SourceVersionStatus
from platform_control.ids import generate_prefixed_id
from platform_control.models.base import Base, TimestampMixin


class SourceVersion(TimestampMixin, Base):
    __tablename__ = "source_versions"

    source_version_id: Mapped[str] = mapped_column(
        primary_key=True, default=lambda: generate_prefixed_id("sv")
    )
    source_id: Mapped[str] = mapped_column(ForeignKey("sources.source_id"))
    extractor_profile_id: Mapped[str | None] = mapped_column(
        ForeignKey("extractor_profiles.extractor_profile_id"), nullable=True
    )
    version_label: Mapped[str] = mapped_column()
    status: Mapped[SourceVersionStatus] = mapped_column(
        Enum(
            SourceVersionStatus,
            native_enum=False,
            values_callable=lambda enum_cls: [member.value for member in enum_cls],
        ),
        default=SourceVersionStatus.DRAFT,
    )
    acquisition_spec: Mapped[dict] = mapped_column(JSON, default=dict)

    source = relationship("Source", back_populates="versions")
    extractor_profile = relationship("ExtractorProfile")
    runs = relationship("Run", back_populates="source_version")
