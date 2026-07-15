from __future__ import annotations

from sqlalchemy import Enum, ForeignKey, UniqueConstraint
from sqlalchemy.orm import Mapped, mapped_column

from platform_control.domain import NormLevel
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
    # Rank of this jurisdiction's own legislation in the hierarchy of norms
    # (ADR-0033). This is what makes a document's `level` derivable from its
    # jurisdiction instead of guessed from its text, and what makes
    # `norm_hierarchy(jurisdiction_id)` answerable. Exported to
    # `contracts/vocabularies/jurisdiction-hierarchy.json` for legal-search.
    level: Mapped[NormLevel] = mapped_column(
        Enum(
            NormLevel,
            native_enum=False,
            values_callable=lambda enum_cls: [member.value for member in enum_cls],
        ),
        default=NormLevel.FEDERAL,
        server_default=NormLevel.FEDERAL.value,
    )
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
    # Optional authority-level compliance override. When set it takes
    # precedence over the jurisdiction's policy so a single jurisdiction can
    # carry different politeness tiers per authority (e.g. Fedlex open-data
    # legislation vs. public-official courts under jur_ch_federal). See #530.
    compliance_policy_id: Mapped[str | None] = mapped_column(
        ForeignKey("compliance_policies.compliance_policy_id"), nullable=True
    )
