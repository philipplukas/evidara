"""Initial platform-control schema.

Revision ID: 20260329_0001
Revises:
Create Date: 2026-03-29
"""

from __future__ import annotations

import sqlalchemy as sa

from alembic import op

revision = "20260329_0001"
down_revision = None
branch_labels = None
depends_on = None


def upgrade() -> None:
    op.create_table(
        "jurisdictions",
        sa.Column("jurisdiction_id", sa.String(), primary_key=True),
        sa.Column("name", sa.String(), nullable=False, unique=True),
        sa.Column("slug", sa.String(), nullable=False, unique=True),
        sa.Column("created_at", sa.DateTime(timezone=True), nullable=False),
        sa.Column("updated_at", sa.DateTime(timezone=True), nullable=False),
    )

    op.create_table(
        "authorities",
        sa.Column("authority_id", sa.String(), primary_key=True),
        sa.Column("jurisdiction_id", sa.String(), nullable=True),
        sa.Column("name", sa.String(), nullable=False, unique=True),
        sa.Column("slug", sa.String(), nullable=False, unique=True),
        sa.Column("created_at", sa.DateTime(timezone=True), nullable=False),
        sa.Column("updated_at", sa.DateTime(timezone=True), nullable=False),
    )

    op.create_table(
        "extractor_profiles",
        sa.Column("extractor_profile_id", sa.String(), primary_key=True),
        sa.Column("name", sa.String(), nullable=False, unique=True),
        sa.Column("source_family", sa.String(), nullable=False),
        sa.Column("version", sa.String(), nullable=False),
        sa.Column("definition", sa.JSON(), nullable=False),
        sa.Column("created_at", sa.DateTime(timezone=True), nullable=False),
        sa.Column("updated_at", sa.DateTime(timezone=True), nullable=False),
    )

    op.create_table(
        "sources",
        sa.Column("source_id", sa.String(), primary_key=True),
        sa.Column("name", sa.String(), nullable=False),
        sa.Column("description", sa.String(), nullable=True),
        sa.Column("jurisdiction_id", sa.String(), nullable=False),
        sa.Column("authority_id", sa.String(), nullable=False),
        sa.Column("source_type", sa.String(), nullable=False),
        sa.Column("document_family", sa.String(), nullable=True),
        sa.Column(
            "status",
            sa.Enum("active", "inactive", "archived", name="source_status"),
            nullable=False,
        ),
        sa.Column("created_at", sa.DateTime(timezone=True), nullable=False),
        sa.Column("updated_at", sa.DateTime(timezone=True), nullable=False),
    )

    op.create_table(
        "source_versions",
        sa.Column("source_version_id", sa.String(), primary_key=True),
        sa.Column("source_id", sa.String(), sa.ForeignKey("sources.source_id"), nullable=False),
        sa.Column(
            "extractor_profile_id",
            sa.String(),
            sa.ForeignKey("extractor_profiles.extractor_profile_id"),
            nullable=True,
        ),
        sa.Column("version_label", sa.String(), nullable=False),
        sa.Column(
            "status",
            sa.Enum(
                "draft",
                "pending_approval",
                "approved",
                "rejected",
                "superseded",
                name="source_version_status",
            ),
            nullable=False,
        ),
        sa.Column("acquisition_spec", sa.JSON(), nullable=False),
        sa.Column("created_at", sa.DateTime(timezone=True), nullable=False),
        sa.Column("updated_at", sa.DateTime(timezone=True), nullable=False),
    )

    op.create_table(
        "runs",
        sa.Column("run_id", sa.String(), primary_key=True),
        sa.Column("source_id", sa.String(), sa.ForeignKey("sources.source_id"), nullable=False),
        sa.Column(
            "source_version_id",
            sa.String(),
            sa.ForeignKey("source_versions.source_version_id"),
            nullable=False,
        ),
        sa.Column("mode", sa.Enum("preview", "production", name="run_mode"), nullable=False),
        sa.Column(
            "status",
            sa.Enum(
                "pending",
                "running",
                "completed",
                "failed",
                "cancelled",
                name="run_status",
            ),
            nullable=False,
        ),
        sa.Column("started_at", sa.DateTime(timezone=True), nullable=True),
        sa.Column("completed_at", sa.DateTime(timezone=True), nullable=True),
        sa.Column("artifacts_count", sa.Integer(), nullable=False),
        sa.Column("captured_resources_count", sa.Integer(), nullable=False),
        sa.Column("failure_reason", sa.String(), nullable=True),
        sa.Column("metadata", sa.JSON(), nullable=False),
        sa.Column("created_at", sa.DateTime(timezone=True), nullable=False),
        sa.Column("updated_at", sa.DateTime(timezone=True), nullable=False),
    )

    op.create_table(
        "provider_jobs",
        sa.Column("provider_job_id", sa.String(), primary_key=True),
        sa.Column("run_id", sa.String(), sa.ForeignKey("runs.run_id"), nullable=False),
        sa.Column("provider", sa.String(), nullable=False),
        sa.Column("external_job_id", sa.String(), nullable=True, unique=True),
        sa.Column(
            "status",
            sa.Enum("accepted", "running", "completed", "failed", name="provider_job_status"),
            nullable=False,
        ),
        sa.Column("request_payload", sa.JSON(), nullable=False),
        sa.Column("response_payload", sa.JSON(), nullable=False),
        sa.Column("last_event_type", sa.String(), nullable=True),
        sa.Column("created_at", sa.DateTime(timezone=True), nullable=False),
        sa.Column("updated_at", sa.DateTime(timezone=True), nullable=False),
    )

    op.create_table(
        "raw_artifacts",
        sa.Column("artifact_id", sa.String(), primary_key=True),
        sa.Column("run_id", sa.String(), sa.ForeignKey("runs.run_id"), nullable=False),
        sa.Column("source_id", sa.String(), sa.ForeignKey("sources.source_id"), nullable=False),
        sa.Column(
            "source_version_id",
            sa.String(),
            sa.ForeignKey("source_versions.source_version_id"),
            nullable=False,
        ),
        sa.Column("storage_path", sa.String(), nullable=False),
        sa.Column("content_type", sa.String(), nullable=False),
        sa.Column("metadata", sa.JSON(), nullable=False),
        sa.Column("created_at", sa.DateTime(timezone=True), nullable=False),
        sa.Column("updated_at", sa.DateTime(timezone=True), nullable=False),
    )

    op.create_table(
        "captured_resources",
        sa.Column("captured_resource_id", sa.String(), primary_key=True),
        sa.Column(
            "artifact_id",
            sa.String(),
            sa.ForeignKey("raw_artifacts.artifact_id"),
            nullable=False,
        ),
        sa.Column("run_id", sa.String(), sa.ForeignKey("runs.run_id"), nullable=False),
        sa.Column("source_id", sa.String(), sa.ForeignKey("sources.source_id"), nullable=False),
        sa.Column(
            "source_version_id",
            sa.String(),
            sa.ForeignKey("source_versions.source_version_id"),
            nullable=False,
        ),
        sa.Column(
            "provider_job_id",
            sa.String(),
            sa.ForeignKey("provider_jobs.provider_job_id"),
            nullable=True,
        ),
        sa.Column("provider", sa.String(), nullable=False),
        sa.Column("source_url", sa.String(), nullable=False),
        sa.Column("final_url", sa.String(), nullable=False),
        sa.Column("title", sa.String(), nullable=True),
        sa.Column("content_type", sa.String(), nullable=False),
        sa.Column("checksum", sa.String(), nullable=True),
        sa.Column("http_status", sa.Integer(), nullable=True),
        sa.Column("discovery_depth", sa.Integer(), nullable=True),
        sa.Column("fetched_at", sa.DateTime(timezone=True), nullable=False),
        sa.Column("metadata", sa.JSON(), nullable=False),
        sa.Column("created_at", sa.DateTime(timezone=True), nullable=False),
        sa.Column("updated_at", sa.DateTime(timezone=True), nullable=False),
    )

    op.create_table(
        "webhook_receipts",
        sa.Column("webhook_receipt_id", sa.String(), primary_key=True),
        sa.Column("provider", sa.String(), nullable=False),
        sa.Column("payload_sha256", sa.String(), nullable=False),
        sa.Column("signature", sa.String(), nullable=True),
        sa.Column("payload", sa.JSON(), nullable=False),
        sa.Column("received_at", sa.DateTime(timezone=True), nullable=False),
        sa.Column("processed_at", sa.DateTime(timezone=True), nullable=True),
        sa.Column("created_at", sa.DateTime(timezone=True), nullable=False),
        sa.Column("updated_at", sa.DateTime(timezone=True), nullable=False),
        sa.UniqueConstraint("provider", "payload_sha256"),
    )


def downgrade() -> None:
    op.drop_table("webhook_receipts")
    op.drop_table("captured_resources")
    op.drop_table("raw_artifacts")
    op.drop_table("provider_jobs")
    op.drop_table("runs")
    op.drop_table("source_versions")
    op.drop_table("sources")
    op.drop_table("extractor_profiles")
    op.drop_table("authorities")
    op.drop_table("jurisdictions")

    op.execute("DROP TYPE IF EXISTS provider_job_status")
    op.execute("DROP TYPE IF EXISTS run_status")
    op.execute("DROP TYPE IF EXISTS run_mode")
    op.execute("DROP TYPE IF EXISTS source_version_status")
    op.execute("DROP TYPE IF EXISTS source_status")
