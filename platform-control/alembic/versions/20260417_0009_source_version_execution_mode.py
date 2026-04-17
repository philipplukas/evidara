"""Add execution_mode to source_versions (off | shadow | live).

Enables shadow-mode dispatch so a new jurisdiction can be exercised end-to-end
through the scheduler, workflow and webhook paths without touching the
upstream server.

Revision ID: 20260417_0009
Revises: 20260411_0008
Create Date: 2026-04-17
"""

from __future__ import annotations

import sqlalchemy as sa

from alembic import op

revision = "20260417_0009"
down_revision = "20260411_0008"
branch_labels = None
depends_on = None


def upgrade() -> None:
    op.add_column(
        "source_versions",
        sa.Column(
            "execution_mode",
            sa.String(),
            nullable=False,
            server_default="live",
        ),
    )


def downgrade() -> None:
    op.drop_column("source_versions", "execution_mode")
