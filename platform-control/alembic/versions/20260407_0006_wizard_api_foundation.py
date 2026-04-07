"""add wizard projects, runs, review tasks, and ledgers

Revision ID: 20260407_0006
Revises: 20260403_0005
Create Date: 2026-04-07
"""

from __future__ import annotations

import sqlalchemy as sa

from alembic import op

revision = "20260407_0006"
down_revision = "20260403_0005"
branch_labels = None
depends_on = None


def upgrade() -> None:
    op.create_table(
        "wizard_projects",
        sa.Column("wizard_project_id", sa.String(), primary_key=True),
        sa.Column("name", sa.String(), nullable=False),
        sa.Column("status", sa.String(), nullable=False),
        sa.Column("scope", sa.JSON(), nullable=False),
        sa.Column("discovery_plan", sa.JSON(), nullable=False),
        sa.Column("created_at", sa.DateTime(timezone=True), nullable=False),
        sa.Column("updated_at", sa.DateTime(timezone=True), nullable=False),
    )

    op.create_table(
        "wizard_runs",
        sa.Column("wizard_run_id", sa.String(), primary_key=True),
        sa.Column(
            "wizard_project_id",
            sa.String(),
            sa.ForeignKey("wizard_projects.wizard_project_id"),
            nullable=False,
        ),
        sa.Column("workflow_id", sa.String(), nullable=True),
        sa.Column("state", sa.String(), nullable=False),
        sa.Column("state_entered_at", sa.DateTime(timezone=True), nullable=False),
        sa.Column("progress", sa.JSON(), nullable=False),
        sa.Column("quality", sa.JSON(), nullable=False),
        sa.Column("health", sa.JSON(), nullable=False),
        sa.Column("failure_reason", sa.String(), nullable=True),
        sa.Column("created_at", sa.DateTime(timezone=True), nullable=False),
        sa.Column("updated_at", sa.DateTime(timezone=True), nullable=False),
    )
    op.create_index("ix_wizard_runs_project_id", "wizard_runs", ["wizard_project_id"])
    op.create_index("ix_wizard_runs_state", "wizard_runs", ["state"])

    op.create_table(
        "review_tasks",
        sa.Column("review_task_id", sa.String(), primary_key=True),
        sa.Column(
            "wizard_run_id",
            sa.String(),
            sa.ForeignKey("wizard_runs.wizard_run_id"),
            nullable=False,
        ),
        sa.Column("argilla_external_id", sa.String(), nullable=False),
        sa.Column("record_id", sa.String(), nullable=True),
        sa.Column("status", sa.String(), nullable=False),
        sa.Column("payload", sa.JSON(), nullable=False),
        sa.Column("decision_payload", sa.JSON(), nullable=True),
        sa.Column("processed_at", sa.DateTime(timezone=True), nullable=True),
        sa.Column("created_at", sa.DateTime(timezone=True), nullable=False),
        sa.Column("updated_at", sa.DateTime(timezone=True), nullable=False),
        sa.UniqueConstraint("argilla_external_id"),
    )
    op.create_index("ix_review_tasks_wizard_run_id", "review_tasks", ["wizard_run_id"])
    op.create_index("ix_review_tasks_status", "review_tasks", ["status"])

    op.create_table(
        "wizard_run_ledgers",
        sa.Column("wizard_run_ledger_id", sa.String(), primary_key=True),
        sa.Column(
            "wizard_run_id",
            sa.String(),
            sa.ForeignKey("wizard_runs.wizard_run_id"),
            nullable=False,
        ),
        sa.Column("state_transitions", sa.JSON(), nullable=False),
        sa.Column("retry_counters", sa.JSON(), nullable=False),
        sa.Column("error_summary", sa.JSON(), nullable=False),
        sa.Column("sla_markers", sa.JSON(), nullable=False),
        sa.Column("published_version", sa.String(), nullable=True),
        sa.Column("created_at", sa.DateTime(timezone=True), nullable=False),
        sa.Column("updated_at", sa.DateTime(timezone=True), nullable=False),
        sa.UniqueConstraint("wizard_run_id"),
    )


def downgrade() -> None:
    op.drop_table("wizard_run_ledgers")
    op.drop_index("ix_review_tasks_status", table_name="review_tasks")
    op.drop_index("ix_review_tasks_wizard_run_id", table_name="review_tasks")
    op.drop_table("review_tasks")
    op.drop_index("ix_wizard_runs_state", table_name="wizard_runs")
    op.drop_index("ix_wizard_runs_project_id", table_name="wizard_runs")
    op.drop_table("wizard_runs")
    op.drop_table("wizard_projects")
