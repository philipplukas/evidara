from __future__ import annotations

from sqlalchemy import ForeignKey, UniqueConstraint
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
    name: Mapped[str] = mapped_column(unique=True)
    slug: Mapped[str] = mapped_column(unique=True)
    compliance_policy_id: Mapped[str | None] = mapped_column(
        ForeignKey("compliance_policies.compliance_policy_id"), nullable=True
    )


class Authority(TimestampMixin, Base):
    __tablename__ = "authorities"
    __table_args__ = (
        UniqueConstraint("name", "jurisdiction_id", name="uq_authorities_name_jurisdiction"),
    )

    authority_id: Mapped[str] = mapped_column(
        primary_key=True, default=lambda: generate_prefixed_id("auth")
    )
    parent_id: Mapped[str | None] = mapped_column(
        ForeignKey("authorities.authority_id"), nullable=True
    )
    jurisdiction_id: Mapped[str | None] = mapped_column(
        ForeignKey("jurisdictions.jurisdiction_id"), nullable=True
    )
    name: Mapped[str] = mapped_column()
    slug: Mapped[str] = mapped_column(unique=True)
