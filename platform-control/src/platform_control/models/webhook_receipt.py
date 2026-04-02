from __future__ import annotations

from datetime import datetime

from sqlalchemy import JSON, UniqueConstraint
from sqlalchemy.orm import Mapped, mapped_column

from platform_control.ids import generate_prefixed_id
from platform_control.models.base import Base, TimestampMixin, utcnow


class WebhookReceipt(TimestampMixin, Base):
    __tablename__ = "webhook_receipts"
    __table_args__ = (UniqueConstraint("provider", "payload_sha256"),)

    webhook_receipt_id: Mapped[str] = mapped_column(
        primary_key=True, default=lambda: generate_prefixed_id("whr")
    )
    provider: Mapped[str] = mapped_column(default="firecrawl")
    payload_sha256: Mapped[str] = mapped_column()
    signature: Mapped[str | None] = mapped_column(nullable=True)
    payload: Mapped[dict] = mapped_column(JSON, default=dict)
    received_at: Mapped[datetime] = mapped_column(default=utcnow)
    processed_at: Mapped[datetime | None] = mapped_column(nullable=True)
