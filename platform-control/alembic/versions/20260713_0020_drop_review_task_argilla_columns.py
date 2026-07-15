"""review_tasks: drop the Argilla-specific columns, rename the dedupe key.

ADR-0031 removes the Argilla integration. The review-task *concept* survives — the
admin app is the review surface and the confidence-band routing policy is retained —
so the table stays. Only what is genuinely Argilla-specific goes:

- ``argilla_enqueued_at`` / ``argilla_enqueue_last_error`` are **dropped**. They exist
  solely to audit the outbound HTTP POST to Argilla (added by 20260408_0007). With the
  client deleted, nothing can ever write them again; keeping them would leave two
  permanently-NULL columns whose names imply an integration that no longer exists.
- ``argilla_external_id`` is **renamed** to ``external_id``, not dropped. It is the
  producer-supplied dedupe key (NOT NULL, UNIQUE) and it is load-bearing: it is what
  makes re-routing the same record a conflict instead of a duplicate queue entry. The
  key outlived Argilla; only its name was Argilla's.

The rename preserves data and the unique constraint. Downgrade is exact.

Revision ID: 20260713_0019
Revises: 20260713_0018
Create Date: 2026-07-13
"""

from __future__ import annotations

import sqlalchemy as sa

from alembic import op

revision = "20260713_0020"
down_revision = "20260713_0019"
branch_labels = None
depends_on = None


def upgrade() -> None:
    # batch_alter_table so SQLite gets its copy-and-move (a plain ALTER on Postgres),
    # matching how every other column change on this schema is done.
    with op.batch_alter_table("review_tasks") as batch_op:
        batch_op.alter_column(
            "argilla_external_id",
            new_column_name="external_id",
            existing_type=sa.String(),
            existing_nullable=False,
        )
        batch_op.drop_column("argilla_enqueue_last_error")
        batch_op.drop_column("argilla_enqueued_at")


def downgrade() -> None:
    with op.batch_alter_table("review_tasks") as batch_op:
        batch_op.add_column(
            sa.Column("argilla_enqueued_at", sa.DateTime(timezone=True), nullable=True)
        )
        batch_op.add_column(sa.Column("argilla_enqueue_last_error", sa.String(), nullable=True))
        batch_op.alter_column(
            "external_id",
            new_column_name="argilla_external_id",
            existing_type=sa.String(),
            existing_nullable=False,
        )
