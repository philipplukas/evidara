from __future__ import annotations

from sqlalchemy import JSON, Enum, ForeignKey
from sqlalchemy.orm import Mapped, mapped_column, relationship

from platform_control.domain import ProviderJobStatus
from platform_control.ids import generate_prefixed_id
from platform_control.models.base import Base, TimestampMixin


class ProviderJob(TimestampMixin, Base):
    __tablename__ = "provider_jobs"

    provider_job_id: Mapped[str] = mapped_column(
        primary_key=True, default=lambda: generate_prefixed_id("pjob")
    )
    run_id: Mapped[str] = mapped_column(ForeignKey("runs.run_id"))
    provider: Mapped[str] = mapped_column(default="firecrawl")
    external_job_id: Mapped[str | None] = mapped_column(nullable=True, unique=True)
    status: Mapped[ProviderJobStatus] = mapped_column(
        Enum(
            ProviderJobStatus,
            native_enum=False,
            values_callable=lambda enum_cls: [member.value for member in enum_cls],
        ),
        default=ProviderJobStatus.ACCEPTED,
    )
    request_payload: Mapped[dict] = mapped_column(JSON, default=dict)
    response_payload: Mapped[dict] = mapped_column(JSON, default=dict)
    last_event_type: Mapped[str | None] = mapped_column(nullable=True)

    run = relationship("Run", back_populates="provider_jobs")
