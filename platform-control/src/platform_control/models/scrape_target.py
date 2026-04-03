from __future__ import annotations

from sqlalchemy import JSON, ForeignKey
from sqlalchemy.orm import Mapped, mapped_column

from platform_control.ids import generate_prefixed_id
from platform_control.models.base import Base, TimestampMixin


class ScrapeTarget(TimestampMixin, Base):
    __tablename__ = "scrape_targets"

    scrape_target_id: Mapped[str] = mapped_column(
        primary_key=True, default=lambda: generate_prefixed_id("stg")
    )
    path: Mapped[str] = mapped_column(unique=True)
    depth: Mapped[int] = mapped_column(default=0)
    jurisdiction_id: Mapped[str | None] = mapped_column(
        ForeignKey("jurisdictions.jurisdiction_id"), nullable=True
    )
    authority_id: Mapped[str | None] = mapped_column(
        ForeignKey("authorities.authority_id"), nullable=True
    )
    selector: Mapped[dict] = mapped_column(JSON, default=dict)
    enabled: Mapped[bool] = mapped_column(default=True)
