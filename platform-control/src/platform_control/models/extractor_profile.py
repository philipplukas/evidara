from __future__ import annotations

from sqlalchemy import JSON
from sqlalchemy.orm import Mapped, mapped_column

from platform_control.ids import generate_prefixed_id
from platform_control.models.base import Base, TimestampMixin


class ExtractorProfile(TimestampMixin, Base):
    __tablename__ = "extractor_profiles"

    extractor_profile_id: Mapped[str] = mapped_column(
        primary_key=True, default=lambda: generate_prefixed_id("exp")
    )
    name: Mapped[str] = mapped_column(unique=True)
    source_family: Mapped[str] = mapped_column()
    version: Mapped[str] = mapped_column(default="v1")
    definition: Mapped[dict] = mapped_column(JSON, default=dict)
