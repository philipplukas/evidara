"""Add compliance_policies table and jurisdictions.compliance_policy_id FK.

Groups the per-jurisdiction politeness knobs (robots mode, rate caps, retention,
attribution, contact URL) so downstream consumers can enforce them uniformly.

Revision ID: 20260417_0010
Revises: 20260417_0009
Create Date: 2026-04-17
"""

from __future__ import annotations

import sqlalchemy as sa

from alembic import op

revision = "20260417_0010"
down_revision = "20260417_0009"
branch_labels = None
depends_on = None


def upgrade() -> None:
    op.create_table(
        "compliance_policies",
        sa.Column("compliance_policy_id", sa.String(), primary_key=True),
        sa.Column("name", sa.String(), nullable=False, unique=True),
        sa.Column("description", sa.String(), nullable=True),
        sa.Column("robots_mode", sa.String(), nullable=False, server_default="strict"),
        sa.Column(
            "max_requests_per_minute_per_host",
            sa.Integer(),
            nullable=False,
            server_default="60",
        ),
        sa.Column("max_concurrent_per_host", sa.Integer(), nullable=False, server_default="2"),
        sa.Column("retention_days", sa.Integer(), nullable=True),
        sa.Column("attribution_required", sa.Boolean(), nullable=False, server_default="0"),
        sa.Column("attribution_text", sa.String(), nullable=True),
        sa.Column("contact_url", sa.String(), nullable=True),
        sa.Column("created_at", sa.DateTime(timezone=True), nullable=False),
        sa.Column("updated_at", sa.DateTime(timezone=True), nullable=False),
    )

    with op.batch_alter_table("jurisdictions") as batch_op:
        batch_op.add_column(sa.Column("compliance_policy_id", sa.String(), nullable=True))
        batch_op.create_foreign_key(
            "fk_jurisdictions_compliance_policy",
            "compliance_policies",
            ["compliance_policy_id"],
            ["compliance_policy_id"],
        )


def downgrade() -> None:
    with op.batch_alter_table("jurisdictions") as batch_op:
        batch_op.drop_constraint("fk_jurisdictions_compliance_policy", type_="foreignkey")
        batch_op.drop_column("compliance_policy_id")
    op.drop_table("compliance_policies")
