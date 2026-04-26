"""Add operators table for auth-resolved principal mapping (M11/B1, #452).

Backs the `Operator` SQLAlchemy model. `auth_principal` maps the
externally-facing identity (constant string per scoped key today; IAP
sub claim or OIDC sub when those land) to a durable `op_*` ID used as
audit reference on corrections and other write actions.

B1 (this migration) only creates the table + seeds two rows
(`op_local_dev`, `op_scoped_operator_key`). B2 (#453) wires the
corrections router to resolve `operator_id` from the principal and
retires the `X-Operator-Id` header fallback.

Revision ID: 20260426_0016
Revises: 20260425_0015
Create Date: 2026-04-26
"""

from __future__ import annotations

from datetime import UTC, datetime

import sqlalchemy as sa

from alembic import op

revision = "20260426_0016"
down_revision = "20260425_0015"
branch_labels = None
depends_on = None


def upgrade() -> None:
    op.create_table(
        "operators",
        sa.Column("operator_id", sa.String(), primary_key=True),
        sa.Column("auth_principal", sa.String(), nullable=False),
        sa.Column("display_name", sa.String(), nullable=False),
        sa.Column("created_at", sa.DateTime(timezone=True), nullable=False),
        sa.Column("disabled_at", sa.DateTime(timezone=True), nullable=True),
        sa.UniqueConstraint("auth_principal", name="uq_operators_auth_principal"),
    )

    operators = sa.table(
        "operators",
        sa.column("operator_id", sa.String()),
        sa.column("auth_principal", sa.String()),
        sa.column("display_name", sa.String()),
        sa.column("created_at", sa.DateTime(timezone=True)),
        sa.column("disabled_at", sa.DateTime(timezone=True)),
    )
    now = datetime.now(UTC)
    op.bulk_insert(
        operators,
        [
            {
                "operator_id": "op_local_dev",
                "auth_principal": "local_dev",
                "display_name": "Local Dev",
                "created_at": now,
                "disabled_at": None,
            },
            {
                "operator_id": "op_scoped_operator_key",
                "auth_principal": "scoped_operator_key",
                "display_name": "Scoped Operator Key",
                "created_at": now,
                "disabled_at": None,
            },
            {
                "operator_id": "op_legacy_full_access",
                "auth_principal": "legacy_full_access",
                "display_name": "Legacy Full-Access Key",
                "created_at": now,
                "disabled_at": None,
            },
        ],
    )


def downgrade() -> None:
    op.drop_table("operators")
