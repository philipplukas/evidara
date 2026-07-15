"""Add authority-level compliance_policy_id override.

Authorities can now bind a compliance policy that overrides their
jurisdiction's policy at resolution time, so a single jurisdiction
(e.g. jur_ch_federal) can carry the Fedlex open-data policy for
legislation while its court authorities (auth_bger/auth_bvger/…) bind a
stricter public-official policy. See #530.

Revision ID: 20260713_0018
Revises: 20260426_0017
Create Date: 2026-07-13
"""

import sqlalchemy as sa

from alembic import op

revision = "20260713_0018"
down_revision = "20260426_0017"
branch_labels = None
depends_on = None


def upgrade() -> None:
    # Mirrors the jurisdictions.compliance_policy_id migration (0010):
    # batch_alter_table performs SQLite's copy-and-move so the FK lands, and
    # runs as a plain ALTER on Postgres.
    with op.batch_alter_table("authorities") as batch_op:
        batch_op.add_column(sa.Column("compliance_policy_id", sa.String(), nullable=True))
        batch_op.create_foreign_key(
            "fk_authorities_compliance_policy",
            "compliance_policies",
            ["compliance_policy_id"],
            ["compliance_policy_id"],
        )


def downgrade() -> None:
    with op.batch_alter_table("authorities") as batch_op:
        batch_op.drop_constraint("fk_authorities_compliance_policy", type_="foreignkey")
        batch_op.drop_column("compliance_policy_id")
