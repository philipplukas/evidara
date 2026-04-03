from __future__ import annotations

from sqlalchemy import ForeignKey
from sqlalchemy.orm import Mapped, mapped_column

from platform_control.ids import generate_prefixed_id
from platform_control.models.base import Base, TimestampMixin


class Jurisdiction(TimestampMixin, Base):
    __tablename__ = "jurisdictions"

    jurisdiction_id: Mapped[str] = mapped_column(
        primary_key=True, default=lambda: generate_prefixed_id("jur")
    )
    parent_id: Mapped[str | None] = mapped_column(
        ForeignKey("jurisdictions.jurisdiction_id"), nullable=True
    )
    path: Mapped[str | None] = mapped_column(unique=True, nullable=True)
    depth: Mapped[int] = mapped_column(default=0)
    name: Mapped[str] = mapped_column(unique=True)
    slug: Mapped[str] = mapped_column(unique=True)


class Authority(TimestampMixin, Base):
    __tablename__ = "authorities"

    authority_id: Mapped[str] = mapped_column(
        primary_key=True, default=lambda: generate_prefixed_id("auth")
    )
    parent_id: Mapped[str | None] = mapped_column(
        ForeignKey("authorities.authority_id"), nullable=True
    )
    path: Mapped[str | None] = mapped_column(unique=True, nullable=True)
    depth: Mapped[int] = mapped_column(default=0)
    jurisdiction_id: Mapped[str | None] = mapped_column(
        ForeignKey("jurisdictions.jurisdiction_id"), nullable=True
    )
    name: Mapped[str] = mapped_column(unique=True)
    slug: Mapped[str] = mapped_column(unique=True)
