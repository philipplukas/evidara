from __future__ import annotations

from datetime import datetime

from sqlalchemy import DateTime, String
from sqlalchemy.orm import Mapped, mapped_column

from platform_control.ids import generate_prefixed_id
from platform_control.models.base import Base, utcnow


class Operator(Base):
    """Authenticated control-plane operator (M11/B1, #452).

    `operator_id` is the durable audit reference recorded on every write
    action (corrections, annotations, run launches). `auth_principal` is
    the externally-facing identity the auth layer resolves to this
    operator at request time — currently a constant string per scoped key
    or local-dev mode; in the future, an IAP claim or OIDC sub.

    Operators are seeded for local-dev (`op_local_dev`) and for the
    operator scoped key (`op_scoped_operator_key`); production setups add
    rows mapping real auth principals to durable `op_*` IDs.
    """

    __tablename__ = "operators"

    operator_id: Mapped[str] = mapped_column(
        String,
        primary_key=True,
        default=lambda: generate_prefixed_id("op"),
    )
    auth_principal: Mapped[str] = mapped_column(String, unique=True, nullable=False)
    display_name: Mapped[str] = mapped_column(String, nullable=False)
    created_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), nullable=False, default=utcnow
    )
    disabled_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True), nullable=True)
