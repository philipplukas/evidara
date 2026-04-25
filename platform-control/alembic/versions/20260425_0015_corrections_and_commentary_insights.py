"""Add corrections audit log and commentary_insights overlay tables.

Backs the Sprint-1 commentary insight overlay API (#421). Corrections are the
append-only audit/queue surface; commentary_insights is the operator-editable
overlay row keyed by ``insight_id`` (matching the contract identifier).

Revision ID: 20260425_0015
Revises: 20260420_0014
Create Date: 2026-04-25
"""

from __future__ import annotations

import sqlalchemy as sa

from alembic import op

revision = "20260425_0015"
down_revision = "20260420_0014"
branch_labels = None
depends_on = None


def upgrade() -> None:
    op.create_table(
        "corrections",
        sa.Column("correction_id", sa.String(), primary_key=True),
        sa.Column("target_entity_type", sa.String(), nullable=False),
        sa.Column("target_entity_id", sa.String(), nullable=False),
        sa.Column("correction_type", sa.String(), nullable=False),
        sa.Column("payload", sa.JSON(), nullable=False),
        sa.Column("original_snapshot", sa.JSON(), nullable=False),
        sa.Column("operator_id", sa.String(), nullable=False),
        sa.Column("pipeline_run_id", sa.String(), nullable=True),
        sa.Column("rationale", sa.String(), nullable=True),
        sa.Column("status", sa.String(), nullable=False, server_default="pending"),
        sa.Column("applied_at", sa.DateTime(timezone=True), nullable=True),
        sa.Column("created_at", sa.DateTime(timezone=True), nullable=False),
        sa.Column("updated_at", sa.DateTime(timezone=True), nullable=False),
    )
    op.create_index(
        "ix_corrections_target_history",
        "corrections",
        ["target_entity_type", "target_entity_id", "created_at"],
    )
    op.create_index(
        "ix_corrections_queue",
        "corrections",
        ["status", "created_at"],
    )

    op.create_table(
        "commentary_insights",
        sa.Column("insight_id", sa.String(), primary_key=True),
        sa.Column("document_id", sa.String(), nullable=False),
        sa.Column("document_revision", sa.Integer(), nullable=False),
        sa.Column("processing_manifest_id", sa.String(), nullable=False),
        sa.Column("section_id", sa.String(), nullable=True),
        sa.Column("citation_id", sa.String(), nullable=True),
        sa.Column("insight_type", sa.String(), nullable=False),
        sa.Column("claim", sa.String(), nullable=False),
        sa.Column("display_text", sa.String(), nullable=False),
        sa.Column("support", sa.JSON(), nullable=False),
        sa.Column("referenced_authorities", sa.JSON(), nullable=False),
        sa.Column("language", sa.String(), nullable=True),
        sa.Column("jurisdiction_id", sa.String(), nullable=True),
        # CONTRACT-PENDING #423: authority_id reserved per the issue body even
        # though the v1 schema does not include it. Drop in a follow-up if the
        # freeze rejects it.
        sa.Column("authority_id", sa.String(), nullable=True),
        sa.Column("confidence", sa.Float(), nullable=False),
        sa.Column("review_state", sa.String(), nullable=False),
        sa.Column("generator", sa.JSON(), nullable=False),
        sa.Column("scores", sa.JSON(), nullable=False),
        sa.Column("metadata", sa.JSON(), nullable=True),
        sa.Column("current_version", sa.Integer(), nullable=False, server_default="1"),
        sa.Column(
            "last_correction_id",
            sa.String(),
            sa.ForeignKey("corrections.correction_id"),
            nullable=True,
        ),
        sa.Column("overlay_updated_at", sa.DateTime(timezone=True), nullable=False),
        sa.Column("created_at", sa.DateTime(timezone=True), nullable=False),
        sa.Column("updated_at", sa.DateTime(timezone=True), nullable=False),
    )
    op.create_index(
        "ix_commentary_insights_document",
        "commentary_insights",
        ["document_id"],
    )
    op.create_index(
        "ix_commentary_insights_jurisdiction",
        "commentary_insights",
        ["jurisdiction_id"],
    )
    op.create_index(
        "ix_commentary_insights_authority",
        "commentary_insights",
        ["authority_id"],
    )


def downgrade() -> None:
    op.drop_index("ix_commentary_insights_authority", table_name="commentary_insights")
    op.drop_index("ix_commentary_insights_jurisdiction", table_name="commentary_insights")
    op.drop_index("ix_commentary_insights_document", table_name="commentary_insights")
    op.drop_table("commentary_insights")
    op.drop_index("ix_corrections_queue", table_name="corrections")
    op.drop_index("ix_corrections_target_history", table_name="corrections")
    op.drop_table("corrections")
