"""Drop dead hierarchy columns and scrape_targets table.

Post-#317, HierarchySyncService is retired. The path/depth columns on
authorities and jurisdictions are no longer written or read. The
scrape_targets table has no writers or readers.

Revision ID: 20260420_0014
Revises: 20260419_0013
Create Date: 2026-04-20
"""

import sqlalchemy as sa

from alembic import op

revision = "20260420_0014"
down_revision = "20260419_0013"
branch_labels = None
depends_on = None


def upgrade() -> None:
    # Drop scrape_targets table (no readers/writers post-#317).
    op.drop_table("scrape_targets")

    # Drop dead path/depth columns on authorities.
    # Use batch_alter_table to avoid hardcoded constraint names that differ
    # between fresh installs and existing DBs.
    with op.batch_alter_table("authorities") as batch_op:
        batch_op.drop_column("path")
        batch_op.drop_column("depth")

    # Drop dead path/depth columns on jurisdictions.
    with op.batch_alter_table("jurisdictions") as batch_op:
        batch_op.drop_column("path")
        batch_op.drop_column("depth")


def downgrade() -> None:
    # Restore jurisdictions path/depth.
    op.add_column(
        "jurisdictions", sa.Column("depth", sa.Integer(), server_default="0", nullable=False)
    )
    op.add_column("jurisdictions", sa.Column("path", sa.String(), nullable=True))
    op.create_unique_constraint("jurisdictions_path_key", "jurisdictions", ["path"])

    # Restore authorities path/depth.
    op.add_column(
        "authorities", sa.Column("depth", sa.Integer(), server_default="0", nullable=False)
    )
    op.add_column("authorities", sa.Column("path", sa.String(), nullable=True))
    op.create_unique_constraint("uq_authorities_path", "authorities", ["path"])

    # Restore scrape_targets table.
    op.create_table(
        "scrape_targets",
        sa.Column("scrape_target_id", sa.String(), primary_key=True),
        sa.Column("path", sa.String(), nullable=False, unique=True),
        sa.Column("depth", sa.Integer(), server_default="0", nullable=False),
        sa.Column(
            "jurisdiction_id",
            sa.String(),
            sa.ForeignKey("jurisdictions.jurisdiction_id"),
            nullable=True,
        ),
        sa.Column(
            "authority_id", sa.String(), sa.ForeignKey("authorities.authority_id"), nullable=True
        ),
        sa.Column("selector", sa.JSON(), server_default="{}"),
        sa.Column("enabled", sa.Boolean(), server_default="1", nullable=False),
        sa.Column("created_at", sa.DateTime(timezone=True), nullable=False),
        sa.Column("updated_at", sa.DateTime(timezone=True), nullable=False),
    )
