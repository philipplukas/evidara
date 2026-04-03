"""add schedules table

Revision ID: 20260403_0005
Revises: 20260403_0004
Create Date: 2026-04-03
"""

from __future__ import annotations

import sqlalchemy as sa

from alembic import op

revision = "20260403_0005"
down_revision = "20260403_0004"
branch_labels = None
depends_on = None


def upgrade() -> None:
    op.create_table(
        "schedules",
        sa.Column("schedule_id", sa.String(), primary_key=True),
        sa.Column(
            "source_id",
            sa.String(),
            sa.ForeignKey("sources.source_id"),
            nullable=False,
        ),
        sa.Column(
            "source_version_id",
            sa.String(),
            sa.ForeignKey("source_versions.source_version_id"),
            nullable=False,
        ),
        sa.Column("cron_expression", sa.String(128), nullable=False),
        sa.Column("timezone", sa.String(64), nullable=False, server_default="UTC"),
        sa.Column("mode", sa.String(), nullable=False, server_default="live"),
        sa.Column(
            "enabled", sa.Boolean(), nullable=False, server_default=sa.text("true")
        ),
        sa.Column("description", sa.String(512), nullable=True),
        sa.Column(
            "last_triggered_at",
            sa.DateTime(timezone=True),
            nullable=True,
        ),
        sa.Column("last_run_id", sa.String(), nullable=True),
        sa.Column(
            "created_at",
            sa.DateTime(timezone=True),
            nullable=False,
            server_default=sa.text("now()"),
        ),
        sa.Column(
            "updated_at",
            sa.DateTime(timezone=True),
            nullable=False,
            server_default=sa.text("now()"),
        ),
    )
    op.create_index(
        "ix_schedules_enabled_source",
        "schedules",
        ["enabled", "source_id"],
    )


def downgrade() -> None:
    op.drop_index("ix_schedules_enabled_source")
    op.drop_table("schedules")
