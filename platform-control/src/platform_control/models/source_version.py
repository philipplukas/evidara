from __future__ import annotations

from sqlalchemy import JSON, Enum, ForeignKey
from sqlalchemy.orm import Mapped, mapped_column, relationship

from platform_control.domain import ExecutionMode, SourceVersionStatus
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
            native_enum=True,
            name="source_version_status",
            values_callable=lambda enum_cls: [member.value for member in enum_cls],
        ),
        default=SourceVersionStatus.DRAFT,
    )
    execution_mode: Mapped[ExecutionMode] = mapped_column(
        Enum(
            ExecutionMode,
            native_enum=False,
            values_callable=lambda enum_cls: [member.value for member in enum_cls],
        ),
        default=ExecutionMode.LIVE,
        server_default=ExecutionMode.LIVE.value,
    )
    acquisition_spec: Mapped[dict] = mapped_column(JSON, default=dict)
    # Blueprint provenance (ADR-0030). Set when the version was created from a
    # `source_blueprints.yaml` template; NULL for versions created from a
    # hand-written acquisition_spec. The run-launch path re-reads the template's
    # `enabled` flag through these, so an operator flipping a template back to
    # `enabled: false` stops existing versions from dispatching.
    overlay_id: Mapped[str | None] = mapped_column(nullable=True)
    provider_template_id: Mapped[str | None] = mapped_column(nullable=True)

    source = relationship("Source", back_populates="versions")
    extractor_profile = relationship("ExtractorProfile")
    runs = relationship("Run", back_populates="source_version")
