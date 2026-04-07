"""review_tasks: argilla outbound enqueue audit columns

Revision ID: 20260408_0007
Revises: 20260407_0006
Create Date: 2026-04-08
"""

from __future__ import annotations

import sqlalchemy as sa

from alembic import op

revision = "20260408_0007"
down_revision = "20260407_0006"
branch_labels = None
depends_on = None


def upgrade() -> None:
    op.add_column(
        "review_tasks",
        sa.Column("argilla_enqueued_at", sa.DateTime(timezone=True), nullable=True),
    )
    op.add_column(
        "review_tasks",
        sa.Column("argilla_enqueue_last_error", sa.String(), nullable=True),
    )


def downgrade() -> None:
    op.drop_column("review_tasks", "argilla_enqueue_last_error")
    op.drop_column("review_tasks", "argilla_enqueued_at")
