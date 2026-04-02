"""Add document lifecycle events table.

Revision ID: 20260402_0003
Revises: 20260402_0002
Create Date: 2026-04-02
"""

from __future__ import annotations

import sqlalchemy as sa

from alembic import op

revision = "20260402_0003"
down_revision = "20260402_0002"
branch_labels = None
depends_on = None


def upgrade() -> None:
    op.create_table(
        "document_lifecycle_events",
        sa.Column("event_id", sa.String(), primary_key=True),
        sa.Column("event_type", sa.String(), nullable=False),
        sa.Column("run_id", sa.String(), nullable=False),
        sa.Column("document_id", sa.String(), nullable=False),
        sa.Column("document_revision", sa.Integer(), nullable=False),
        sa.Column("processing_manifest_id", sa.String(), nullable=False),
        sa.Column("processing_version", sa.String(), nullable=True),
        sa.Column("lifecycle_status", sa.String(), nullable=True),
        sa.Column("reason_code", sa.String(), nullable=True),
        sa.Column("reason_summary", sa.String(), nullable=True),
        sa.Column("search_disposition", sa.String(), nullable=True),
        sa.Column("occurred_at", sa.DateTime(timezone=True), nullable=False),
        sa.Column("created_at", sa.DateTime(timezone=True), nullable=False),
        sa.Column("updated_at", sa.DateTime(timezone=True), nullable=False),
    )
    op.create_index("ix_document_lifecycle_events_run_id", "document_lifecycle_events", ["run_id"])
    op.create_index(
        "ix_document_lifecycle_events_document_id",
        "document_lifecycle_events",
        ["document_id"],
    )


def downgrade() -> None:
    op.drop_index(
        "ix_document_lifecycle_events_document_id",
        table_name="document_lifecycle_events",
    )
    op.drop_index("ix_document_lifecycle_events_run_id", table_name="document_lifecycle_events")
    op.drop_table("document_lifecycle_events")
