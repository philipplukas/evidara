from __future__ import annotations

from datetime import datetime

from sqlalchemy import DateTime, Enum, Integer
from sqlalchemy.orm import Mapped, mapped_column

from platform_control.domain import ProcessingStatus
from platform_control.models.base import Base, TimestampMixin


class ProcessingStatusUpdate(TimestampMixin, Base):
    __tablename__ = "processing_status_updates"

    event_id: Mapped[str] = mapped_column(primary_key=True)
    run_id: Mapped[str] = mapped_column(index=True)
    processing_manifest_id: Mapped[str] = mapped_column(index=True)
    processing_version: Mapped[str] = mapped_column()
    status: Mapped[ProcessingStatus] = mapped_column(
        Enum(ProcessingStatus, native_enum=False),
        default=ProcessingStatus.ACCEPTED,
    )
    occurred_at: Mapped[datetime] = mapped_column(DateTime(timezone=True))
    source_snapshot_id: Mapped[str | None] = mapped_column(nullable=True)
    bundle_manifest_id: Mapped[str | None] = mapped_column(nullable=True)
    document_id: Mapped[str | None] = mapped_column(nullable=True)
    document_revision: Mapped[int | None] = mapped_column(Integer, nullable=True)
    error_code: Mapped[str | None] = mapped_column(nullable=True)
    error_summary: Mapped[str | None] = mapped_column(nullable=True)
