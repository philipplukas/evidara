"""Add blueprint_template_overrides — the operator-reachable enablement key (#632).

ADR-0030's two-key lock names `enabled` "the config-owner key an operator flips"
after capturing acceptance-run evidence. Until now both keys lived in the repo:
`enabled` was YAML inside the Python package, so flipping it meant a PR + a
deploy — an engineer, per template. That pins #628's cost-of-the-Nth-source
metric to a source file and breaks the operator-not-engineer thesis.

This table is the operator-reachable half. A row overrides the shipped
`source_blueprints.yaml` default for one (overlay_id, provider_template_id)
pair; absence means "use the shipped default" (fail-closed). updated_by / note /
updated_at are the audit trail. The code-owner key (`live_ready`) stays in code.

Revision ID: 20260717_0022
Revises: 20260714_0021
Create Date: 2026-07-17
"""

import sqlalchemy as sa

from alembic import op

revision = "20260717_0022"
down_revision = "20260714_0021"
branch_labels = None
depends_on = None


def upgrade() -> None:
    op.create_table(
        "blueprint_template_overrides",
        sa.Column("override_id", sa.String(), nullable=False),
        sa.Column("overlay_id", sa.String(), nullable=False),
        sa.Column("provider_template_id", sa.String(), nullable=False),
        sa.Column("enabled", sa.Boolean(), nullable=False),
        sa.Column("note", sa.String(), nullable=True),
        sa.Column("updated_by", sa.String(), nullable=True),
        sa.Column("created_at", sa.DateTime(timezone=True), nullable=False),
        sa.Column("updated_at", sa.DateTime(timezone=True), nullable=False),
        sa.PrimaryKeyConstraint("override_id"),
        sa.UniqueConstraint(
            "overlay_id",
            "provider_template_id",
            name="uq_blueprint_template_override_key",
        ),
    )


def downgrade() -> None:
    op.drop_table("blueprint_template_overrides")
