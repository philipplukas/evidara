from __future__ import annotations

from sqlalchemy import Enum
from sqlalchemy.orm import Mapped, mapped_column, relationship

from platform_control.domain import SourceStatus
from platform_control.ids import generate_prefixed_id
from platform_control.models.base import Base, TimestampMixin


class Source(TimestampMixin, Base):
    __tablename__ = "sources"

    source_id: Mapped[str] = mapped_column(
        primary_key=True, default=lambda: generate_prefixed_id("src")
    )
    name: Mapped[str] = mapped_column()
    description: Mapped[str | None] = mapped_column(nullable=True)
    jurisdiction_id: Mapped[str] = mapped_column()
    authority_id: Mapped[str] = mapped_column()
    source_type: Mapped[str] = mapped_column(default="website")
    document_family: Mapped[str | None] = mapped_column(nullable=True)
    status: Mapped[SourceStatus] = mapped_column(
        Enum(SourceStatus, native_enum=False), default=SourceStatus.ACTIVE
    )

    versions = relationship("SourceVersion", back_populates="source")
    runs = relationship("Run", back_populates="source")
