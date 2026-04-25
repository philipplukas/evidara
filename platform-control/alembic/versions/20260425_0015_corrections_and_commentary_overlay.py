"""Add corrections + commentary_insights tables.

Backs the structured-corrections HITL track frozen in PR #434
(`contracts/schemas/corrections.json`, `contracts/schemas/commentary-insight.schema.json`).

The `corrections` table is the durable audit log: every operator-raised or
pipeline-raised correction lives here as a row in `pending` /  `applied` /
`rejected` / `superseded`.

The `commentary_insights` table is the operator-facing read model that
caches the current state of each commentary insight after corrections have
been applied. It is populated by document-intelligence runs and amended by
applied corrections; running the projection rebuild is what keeps it in
sync with the upstream pipeline.

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
        sa.Column("language", sa.String(), nullable=True),
        sa.Column("jurisdiction_id", sa.String(), nullable=True),
        sa.Column("confidence", sa.Float(), nullable=False),
        sa.Column("review_state", sa.String(), nullable=False),
        # JSON columns capture array/object shapes from the upstream
        # commentary-insight schema. Using JSON (not JSONB) so SQLite
        # tests continue to work; Postgres stores it as JSONB at the
        # cluster level when configured. Equivalent to processing_manifest.
        sa.Column("support", sa.JSON(), nullable=False),
        sa.Column("referenced_authorities", sa.JSON(), nullable=False),
        sa.Column("jurisdiction_ids", sa.JSON(), nullable=False),
        sa.Column("authority_ids", sa.JSON(), nullable=False),
        sa.Column("source_document_ids", sa.JSON(), nullable=False),
        sa.Column("generator", sa.JSON(), nullable=False),
        sa.Column("scores", sa.JSON(), nullable=False),
        sa.Column("metadata_json", sa.JSON(), nullable=True),
        # Operator-overlay state. `last_correction_id` lets the read API
        # surface "current revision" without a JOIN against corrections.
        sa.Column("overlay_revision", sa.Integer(), nullable=False, server_default="1"),
        sa.Column("last_correction_id", sa.String(), nullable=True),
        sa.Column("created_at", sa.DateTime(timezone=True), nullable=False),
        sa.Column("updated_at", sa.DateTime(timezone=True), nullable=False),
    )
    op.create_index(
        "ix_commentary_insights_document_id",
        "commentary_insights",
        ["document_id"],
    )
    op.create_index(
        "ix_commentary_insights_review_state",
        "commentary_insights",
        ["review_state"],
    )

    op.create_table(
        "corrections",
        sa.Column("correction_id", sa.String(), primary_key=True),
        sa.Column("target_entity_type", sa.String(), nullable=False),
        sa.Column("target_entity_id", sa.String(), nullable=False),
        sa.Column("correction_type", sa.String(), nullable=False),
        sa.Column("payload", sa.JSON(), nullable=False),
        sa.Column("original_snapshot", sa.JSON(), nullable=True),
        sa.Column("operator_id", sa.String(), nullable=False),
        sa.Column("pipeline_run_id", sa.String(), nullable=True),
        sa.Column("rationale", sa.String(), nullable=True),
        sa.Column("status", sa.String(), nullable=False, server_default="pending"),
        sa.Column("created_at", sa.DateTime(timezone=True), nullable=False),
        sa.Column("applied_at", sa.DateTime(timezone=True), nullable=True),
    )
    # Composite index supports the most common admin queue queries:
    # "pending corrections for this insight" and "all corrections targeting
    # this entity, newest first".
    op.create_index(
        "ix_corrections_target",
        "corrections",
        ["target_entity_type", "target_entity_id"],
    )
    op.create_index("ix_corrections_status", "corrections", ["status"])
    op.create_index("ix_corrections_operator_id", "corrections", ["operator_id"])

    # last_correction_id is a hint, not an enforced FK — corrections can be
    # `superseded` and the overlay row keeps pointing at the most recent
    # applied correction. We leave the FK off intentionally so admin
    # snapshots can survive correction GC without orphaning.


def downgrade() -> None:
    op.drop_index("ix_corrections_operator_id", table_name="corrections")
    op.drop_index("ix_corrections_status", table_name="corrections")
    op.drop_index("ix_corrections_target", table_name="corrections")
    op.drop_table("corrections")

    op.drop_index("ix_commentary_insights_review_state", table_name="commentary_insights")
    op.drop_index("ix_commentary_insights_document_id", table_name="commentary_insights")
    op.drop_table("commentary_insights")
