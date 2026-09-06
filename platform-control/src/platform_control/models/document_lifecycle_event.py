from __future__ import annotations

from datetime import datetime

from sqlalchemy import JSON, DateTime, Integer, String
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
    #: Per-stage timings and counts from document-intelligence, denormalised off
    #: `document.processed` so the run detail can render a stage timeline without
    #: reading the lakehouse.
    #:
    #: NULL and `[]` are different: NULL is a row written before the producer
    #: emitted stages (or by a producer that does not), `[]` would be a claim
    #: that the pipeline ran none. Only NULL is ever written for "not recorded" —
    #: `_stages_for_storage` keeps that distinction, and the read model renders
    #: NULL as unrecorded rather than as zero work.
    stages: Mapped[list | None] = mapped_column(JSON, nullable=True)
    occurred_at: Mapped[datetime] = mapped_column(DateTime(timezone=True))
