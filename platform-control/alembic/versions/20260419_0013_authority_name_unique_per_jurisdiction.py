"""Relax authorities.name UNIQUE to (name, jurisdiction_id).

The global UNIQUE constraint on authorities.name prevents seeding authorities
with the same name in different jurisdictions (e.g. "Bundesverwaltungsgericht"
in both CH and DE).  Replace it with a composite unique on (name, jurisdiction_id).

Revision ID: 20260419_0013
Revises: 20260417_0012
Create Date: 2026-04-19
"""

from alembic import op

revision = "20260419_0013"
down_revision = "20260417_0012"
branch_labels = None
depends_on = None


def upgrade() -> None:
    op.drop_constraint("authorities_name_key", "authorities", type_="unique")
    op.create_unique_constraint(
        "uq_authorities_name_jurisdiction",
        "authorities",
        ["name", "jurisdiction_id"],
    )


def downgrade() -> None:
    op.drop_constraint("uq_authorities_name_jurisdiction", "authorities", type_="unique")
    op.create_unique_constraint("authorities_name_key", "authorities", ["name"])
