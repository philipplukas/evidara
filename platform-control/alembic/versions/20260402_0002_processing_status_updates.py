"""Add processing status updates read-model table.

Revision ID: 20260402_0002
Revises: 20260329_0001
Create Date: 2026-04-02
"""

from __future__ import annotations

import sqlalchemy as sa

from alembic import op

revision = "20260402_0002"
down_revision = "20260329_0001"
branch_labels = None
depends_on = None


def upgrade() -> None:
    op.create_table(
        "processing_status_updates",
        sa.Column("event_id", sa.String(), primary_key=True),
        sa.Column("run_id", sa.String(), nullable=False),
        sa.Column("processing_manifest_id", sa.String(), nullable=False),
        sa.Column("processing_version", sa.String(), nullable=False),
        sa.Column(
            "status",
            sa.Enum(
                "accepted",
                "processing",
                "canonical_ready",
                "failed",
                "withdrawn",
                "skipped_duplicate",
                name="processing_status",
            ),
            nullable=False,
        ),
        sa.Column("occurred_at", sa.DateTime(timezone=True), nullable=False),
        sa.Column("source_snapshot_id", sa.String(), nullable=True),
        sa.Column("bundle_manifest_id", sa.String(), nullable=True),
        sa.Column("document_id", sa.String(), nullable=True),
        sa.Column("document_revision", sa.Integer(), nullable=True),
        sa.Column("error_code", sa.String(), nullable=True),
        sa.Column("error_summary", sa.String(), nullable=True),
        sa.Column("created_at", sa.DateTime(timezone=True), nullable=False),
        sa.Column("updated_at", sa.DateTime(timezone=True), nullable=False),
    )
    op.create_index(
        "ix_processing_status_updates_run_id",
        "processing_status_updates",
        ["run_id"],
    )
    op.create_index(
        "ix_processing_status_updates_processing_manifest_id",
        "processing_status_updates",
        ["processing_manifest_id"],
    )


def downgrade() -> None:
    op.drop_index(
        "ix_processing_status_updates_processing_manifest_id",
        table_name="processing_status_updates",
    )
    op.drop_index("ix_processing_status_updates_run_id", table_name="processing_status_updates")
    op.drop_table("processing_status_updates")
    op.execute("DROP TYPE IF EXISTS processing_status")
