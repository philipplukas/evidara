"""Add hierarchy fields and scrape targets.

Revision ID: 20260403_0004
Revises: 20260402_0003
Create Date: 2026-04-03
"""

from __future__ import annotations

import sqlalchemy as sa

from alembic import op

revision = "20260403_0004"
down_revision = "20260402_0003"
branch_labels = None
depends_on = None


def upgrade() -> None:
    op.add_column("jurisdictions", sa.Column("parent_id", sa.String(), nullable=True))
    op.add_column("jurisdictions", sa.Column("path", sa.String(), nullable=True))
    op.add_column(
        "jurisdictions",
        sa.Column("depth", sa.Integer(), nullable=False, server_default="0"),
    )
    op.create_foreign_key(
        "fk_jurisdictions_parent_id",
        "jurisdictions",
        "jurisdictions",
        ["parent_id"],
        ["jurisdiction_id"],
    )
    op.create_unique_constraint("uq_jurisdictions_path", "jurisdictions", ["path"])

    op.add_column("authorities", sa.Column("parent_id", sa.String(), nullable=True))
    op.add_column("authorities", sa.Column("path", sa.String(), nullable=True))
    op.add_column(
        "authorities",
        sa.Column("depth", sa.Integer(), nullable=False, server_default="0"),
    )
    op.create_foreign_key(
        "fk_authorities_parent_id",
        "authorities",
        "authorities",
        ["parent_id"],
        ["authority_id"],
    )
    op.create_unique_constraint("uq_authorities_path", "authorities", ["path"])

    op.create_table(
        "scrape_targets",
        sa.Column("scrape_target_id", sa.String(), primary_key=True),
        sa.Column("path", sa.String(), nullable=False),
        sa.Column("depth", sa.Integer(), nullable=False, server_default="0"),
        sa.Column(
            "jurisdiction_id",
            sa.String(),
            sa.ForeignKey("jurisdictions.jurisdiction_id"),
            nullable=True,
        ),
        sa.Column(
            "authority_id",
            sa.String(),
            sa.ForeignKey("authorities.authority_id"),
            nullable=True,
        ),
        sa.Column("selector", sa.JSON(), nullable=False),
        sa.Column("enabled", sa.Boolean(), nullable=False, server_default=sa.true()),
        sa.Column(
            "created_at",
            sa.DateTime(timezone=True),
            nullable=False,
            server_default=sa.text("CURRENT_TIMESTAMP"),
        ),
        sa.Column(
            "updated_at",
            sa.DateTime(timezone=True),
            nullable=False,
            server_default=sa.text("CURRENT_TIMESTAMP"),
        ),
        sa.UniqueConstraint("path", name="uq_scrape_targets_path"),
    )


def downgrade() -> None:
    op.drop_table("scrape_targets")

    op.drop_constraint("uq_authorities_path", "authorities", type_="unique")
    op.drop_constraint("fk_authorities_parent_id", "authorities", type_="foreignkey")
    op.drop_column("authorities", "depth")
    op.drop_column("authorities", "path")
    op.drop_column("authorities", "parent_id")

    op.drop_constraint("uq_jurisdictions_path", "jurisdictions", type_="unique")
    op.drop_constraint("fk_jurisdictions_parent_id", "jurisdictions", type_="foreignkey")
    op.drop_column("jurisdictions", "depth")
    op.drop_column("jurisdictions", "path")
    op.drop_column("jurisdictions", "parent_id")
