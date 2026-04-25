"""Add rescore-loop columns to corrections (#427).

Extends the ``corrections`` table introduced in 0015 with the workflow / run /
outcome columns the targeted-rescore loop persists. Also makes ``operator_id``
nullable since system-emitted ``rescore_request`` rows have no operator.

Revision ID: 20260425_0016
Revises: 20260425_0015
Create Date: 2026-04-25
"""

from __future__ import annotations

import sqlalchemy as sa

from alembic import op

revision = "20260425_0016"
down_revision = "20260425_0015"
branch_labels = None
depends_on = None


def upgrade() -> None:
    op.alter_column("corrections", "operator_id", existing_type=sa.String(), nullable=True)
    op.add_column("corrections", sa.Column("source_correction_id", sa.String(), nullable=True))
    op.add_column("corrections", sa.Column("workflow_id", sa.String(), nullable=True))
    op.add_column("corrections", sa.Column("workflow_run_id", sa.String(), nullable=True))
    op.add_column("corrections", sa.Column("resulting_run_id", sa.String(), nullable=True))
    op.add_column("corrections", sa.Column("resulting_extraction_id", sa.String(), nullable=True))
    op.add_column(
        "corrections", sa.Column("completed_at", sa.DateTime(timezone=True), nullable=True)
    )
    # Idempotency guard for rescore_request rows. A given (source_correction,
    # target_entity) pair must produce at most one rescore audit row; the
    # service layer also early-returns on the existing row but the unique
    # index is the safety net under concurrent POSTs.
    op.create_index(
        "uq_corrections_rescore_idempotency",
        "corrections",
        ["source_correction_id", "target_entity_id"],
        unique=True,
        postgresql_where=sa.text("correction_type = 'rescore_request'"),
    )


def downgrade() -> None:
    op.drop_index("uq_corrections_rescore_idempotency", table_name="corrections")
    op.drop_column("corrections", "completed_at")
    op.drop_column("corrections", "resulting_extraction_id")
    op.drop_column("corrections", "resulting_run_id")
    op.drop_column("corrections", "workflow_run_id")
    op.drop_column("corrections", "workflow_id")
    op.drop_column("corrections", "source_correction_id")
    op.alter_column("corrections", "operator_id", existing_type=sa.String(), nullable=False)
