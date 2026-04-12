"""Add corpora table for first-class corpus/tenant/scope entities.

Revision ID: 20260411_0008
Revises: 20260408_0007
Create Date: 2026-04-11
"""

from __future__ import annotations

import sqlalchemy as sa

from alembic import op

revision = "20260411_0008"
down_revision = "20260408_0007"
branch_labels = None
depends_on = None


def upgrade() -> None:
    op.create_table(
        "corpora",
        sa.Column("corpus_id", sa.String(), primary_key=True),
        sa.Column("name", sa.String(), nullable=False),
        sa.Column("description", sa.String(), nullable=True),
        sa.Column("tenant_id", sa.String(), nullable=False),
        sa.Column("scope_type", sa.String(), nullable=False, server_default="global_public"),
        sa.Column("status", sa.String(), nullable=False, server_default="active"),
        sa.Column("created_at", sa.DateTime(timezone=True), nullable=False),
        sa.Column("updated_at", sa.DateTime(timezone=True), nullable=False),
    )
    op.create_index("ix_corpora_tenant_id", "corpora", ["tenant_id"])
    op.create_index("ix_corpora_status", "corpora", ["status"])


def downgrade() -> None:
    op.drop_index("ix_corpora_status", table_name="corpora")
    op.drop_index("ix_corpora_tenant_id", table_name="corpora")
    op.drop_table("corpora")
