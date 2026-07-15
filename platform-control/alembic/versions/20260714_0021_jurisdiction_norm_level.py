"""Add `level` (hierarchy of norms) to jurisdictions.

ADR-0033 / #583. Nothing in the system encoded that municipal law sits under
cantonal law sits under federal law, so `norm_hierarchy(jurisdiction_id)` was
unanswerable. The jurisdiction is the honest source for a norm's level — the
alternative is guessing it from the document text — so the rank lands here and
documents derive from it.

The backfill is structural, not a guess: it reads the existing
`parent_id` tree that the reference seed already maintains.

  - roots (`parent_id IS NULL`)                     -> federal
  - `jur_*_federal` (federal scope of a country)    -> federal
  - depth 1 under a root (cantons, Laender)         -> cantonal
  - depth 2 (communes under a canton/Land)          -> municipal
  - `jur_eu`                                        -> international

`seed_reference_data` rewrites every row from
`seeds/reference/jurisdictions.yaml` on the next run, so the backfill only has
to be correct for the window between migrate and seed.

Revision ID: 20260714_0021
Revises: 20260713_0020
Create Date: 2026-07-14
"""

import sqlalchemy as sa

from alembic import op

revision = "20260714_0021"
down_revision = "20260713_0020"
branch_labels = None
depends_on = None


def upgrade() -> None:
    with op.batch_alter_table("jurisdictions") as batch_op:
        batch_op.add_column(
            sa.Column(
                "level",
                sa.String(),
                nullable=False,
                server_default="federal",
            )
        )

    # Depth-based backfill over the existing parent tree. Ordered
    # coarse-to-fine: later statements overwrite earlier ones.
    op.execute(
        sa.text(
            """
            UPDATE jurisdictions
               SET level = 'cantonal'
             WHERE parent_id IS NOT NULL
               AND parent_id IN (
                     SELECT jurisdiction_id FROM jurisdictions WHERE parent_id IS NULL
                   )
               AND jurisdiction_id NOT LIKE '%\\_federal' ESCAPE '\\'
            """
        )
    )
    op.execute(
        sa.text(
            """
            UPDATE jurisdictions
               SET level = 'municipal'
             WHERE parent_id IS NOT NULL
               AND parent_id IN (
                     SELECT child.jurisdiction_id
                       FROM jurisdictions AS child
                       JOIN jurisdictions AS root
                         ON child.parent_id = root.jurisdiction_id
                      WHERE root.parent_id IS NULL
                        AND child.jurisdiction_id NOT LIKE '%\\_federal' ESCAPE '\\'
                   )
            """
        )
    )
    op.execute(sa.text("UPDATE jurisdictions SET level = 'international' WHERE slug = 'eu'"))


def downgrade() -> None:
    with op.batch_alter_table("jurisdictions") as batch_op:
        batch_op.drop_column("level")
