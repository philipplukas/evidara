from __future__ import annotations

from sqlalchemy import Enum
from sqlalchemy.orm import Mapped, mapped_column

from platform_control.ids import generate_prefixed_id
from platform_control.models.base import Base, TimestampMixin


class CorpusStatus(str):
    """Plain string constants for corpus status — avoids an extra StrEnum import cycle."""


class Corpus(TimestampMixin, Base):
    """A named corpus that groups sources under a shared tenant/scope identity.

    ``tenant_id`` and ``scope_type`` were previously frozen as string literals inside
    ``BaseAcquisitionSpec``.  This entity makes them first-class so operators can create
    and manage multiple corpora without editing every source version's acquisition config.

    ``source_versions`` continue to reference ``corpus_id`` as a plain string in their
    JSON acquisition spec; a future migration can add the FK column.
    """

    __tablename__ = "corpora"

    corpus_id: Mapped[str] = mapped_column(
        primary_key=True,
        default=lambda: generate_prefixed_id("cps"),
    )
    name: Mapped[str] = mapped_column(nullable=False)
    description: Mapped[str | None] = mapped_column(nullable=True)
    tenant_id: Mapped[str] = mapped_column(nullable=False)
    scope_type: Mapped[str] = mapped_column(
        Enum(
            "global_public",
            "tenant_private",
            "tenant_shared",
            name="corpus_scope_type",
            native_enum=False,
        ),
        nullable=False,
        default="global_public",
    )
    status: Mapped[str] = mapped_column(
        Enum(
            "active",
            "archived",
            name="corpus_status",
            native_enum=False,
        ),
        nullable=False,
        default="active",
    )
