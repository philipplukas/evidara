from __future__ import annotations

from datetime import datetime

from sqlalchemy import DateTime, Integer, String
from sqlalchemy.orm import Mapped, mapped_column

from platform_control.models.base import Base, TimestampMixin


class DocumentLifecycleEvent(TimestampMixin, Base):
    __tablename__ = "document_lifecycle_events"

    event_id: Mapped[str] = mapped_column(primary_key=True)
    event_type: Mapped[str] = mapped_column(String, nullable=False)
    run_id: Mapped[str] = mapped_column(index=True)
    document_id: Mapped[str] = mapped_column(index=True)
    document_revision: Mapped[int] = mapped_column(Integer, nullable=False)
    processing_manifest_id: Mapped[str] = mapped_column(String, nullable=False)
    processing_version: Mapped[str | None] = mapped_column(String, nullable=True)
    lifecycle_status: Mapped[str | None] = mapped_column(String, nullable=True)
    reason_code: Mapped[str | None] = mapped_column(String, nullable=True)
    reason_summary: Mapped[str | None] = mapped_column(String, nullable=True)
    search_disposition: Mapped[str | None] = mapped_column(String, nullable=True)
    occurred_at: Mapped[datetime] = mapped_column(DateTime(timezone=True))
