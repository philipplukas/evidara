"""Record blueprint provenance on source_versions.

The ADR-0030 two-key lock needs to know which `source_blueprints.yaml`
template a source version came from, so the run-launch path can re-read that
template's `enabled` flag at dispatch time. Versions created from a
hand-written acquisition_spec leave both columns NULL (only the provider-side
`live_ready` key applies to them). See #559.

Revision ID: 20260713_0019
Revises: 20260713_0018
Create Date: 2026-07-13
"""

import sqlalchemy as sa

from alembic import op

revision = "20260713_0019"
down_revision = "20260713_0018"
branch_labels = None
depends_on = None


def upgrade() -> None:
    with op.batch_alter_table("source_versions") as batch_op:
        batch_op.add_column(sa.Column("overlay_id", sa.String(), nullable=True))
        batch_op.add_column(sa.Column("provider_template_id", sa.String(), nullable=True))


def downgrade() -> None:
    with op.batch_alter_table("source_versions") as batch_op:
        batch_op.drop_column("provider_template_id")
        batch_op.drop_column("overlay_id")
