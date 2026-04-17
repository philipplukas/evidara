"""Add AIMD corridor fields to compliance_policies (min/start rpm).

Supports the adaptive rate limiter that climbs toward ``max`` on clean traffic
and drops toward ``min`` on 429/503/connection-error pressure. Both columns are
nullable so existing rows keep behaving exactly as they do today (static cap);
when set they enable probing within the corridor.

Revision ID: 20260417_0011
Revises: 20260417_0010
Create Date: 2026-04-17
"""

from __future__ import annotations

import sqlalchemy as sa

from alembic import op

revision = "20260417_0011"
down_revision = "20260417_0010"
branch_labels = None
depends_on = None


def upgrade() -> None:
    with op.batch_alter_table("compliance_policies") as batch_op:
        batch_op.add_column(
            sa.Column("min_requests_per_minute_per_host", sa.Integer(), nullable=True)
        )
        batch_op.add_column(
            sa.Column("start_requests_per_minute_per_host", sa.Integer(), nullable=True)
        )


def downgrade() -> None:
    with op.batch_alter_table("compliance_policies") as batch_op:
        batch_op.drop_column("start_requests_per_minute_per_host")
        batch_op.drop_column("min_requests_per_minute_per_host")
