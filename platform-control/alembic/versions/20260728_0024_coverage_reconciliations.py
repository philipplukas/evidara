"""Add `coverage_reconciliations` — the acquisition ledger's stored attribution (#816).

Every acquisition template reports success without saying what fraction of a corpus it
covers. #818 produced the first real denominator — the LexFind digit-union enumeration
reads the source's own published count (ZH: 1377) and compares it to what discovery
found — but the numbers land in `provider_jobs.response_payload`, an opaque JSON column
nothing reads. This table is where they become answerable.

WHY A TABLE AND NOT A QUERY OVER THE EXISTING PAYLOAD
-----------------------------------------------------
The full argument is in `models/coverage_reconciliation.py`. The short version, and the
reason it is a migration rather than a service function:

**A row here is a decision, not a cache.** The payload records `entity_id: 26`; it never
records `jur_ch_zh`. The mapping from one to the other runs through
`Source.jurisdiction_id`, which is mutable state read at some moment in time. Computing
the ledger on demand would mean re-evaluating that mapping on every render, so
re-pointing a source would retroactively re-attribute a past measurement of Zürich's
published total to a different canton — silently, and with no record that it had changed.
Persisting the attribution in the same transaction as the measurement is what makes the
row falsifiable later. `test_reconciliation_survives_a_source_rejurisdiction` pins it.

The other disqualifier for computing: `provider_jobs` grows one row per run forever, so
any on-demand read needs a time window — and a window makes "never measured" and
"measured before the window" indistinguishable. That is ADR-0042's four-causes-of-an-
empty-result failure rebuilt inside the endpoint meant to fix it.

NO BACKFILL, AND WHY THE EMPTY TABLE IS HONEST
----------------------------------------------
Every LexFind template ships `enabled: false`, so there is nothing to backfill — zero
reconciliations exist today. An empty ledger must not read as "we measured and found
nothing", so the read model reports `reconciliations_recorded_since` (this migration's
own horizon) rather than rendering an empty table that looks like a broken endpoint.

THE INDEX
---------
`captured_resources.source_id` carries no index today (only `artifact_id`, `run_id`,
`provider_job_id`). The ledger's `acquired` aggregation groups by it, so it would be a
full scan on a table that grows with every captured document — 1377 rows for one ZH
sweep alone. Added here rather than left as a surprise.

Note for whoever changes this next: `tests/conftest.py` builds the schema with
`Base.metadata.create_all` against SQLite, so a model without a migration passes the
entire suite and fails only in production. Nothing in CI compares the two. Verify by
hand with `alembic upgrade head` against a real Postgres.

Revision ID: 20260728_0024
Revises: 20260720_0023
Create Date: 2026-07-28
"""

import sqlalchemy as sa

from alembic import op

revision = "20260728_0024"
down_revision = "20260720_0023"
branch_labels = None
depends_on = None


def upgrade() -> None:
    op.create_table(
        "coverage_reconciliations",
        sa.Column("reconciliation_id", sa.String(), primary_key=True),
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
        # Nullable: a multi-entity run cannot be attributed to the single jurisdiction
        # its source names, and the row is still written so the attempt leaves evidence.
        sa.Column(
            "jurisdiction_id",
            sa.String(),
            sa.ForeignKey("jurisdictions.jurisdiction_id"),
            nullable=True,
        ),
        # VARCHAR, not a native enum: the models declare `native_enum=False`, and a
        # native type here would recreate the two-producers-of-one-schema hazard
        # 20260720_0023 was written to correct.
        sa.Column("attribution_status", sa.String(), nullable=False, server_default="attributed"),
        sa.Column("entity_id", sa.String(), nullable=True),
        sa.Column("strategy", sa.String(), nullable=True),
        sa.Column("denominator_tier", sa.String(), nullable=False, server_default="none"),
        sa.Column("denominator_source", sa.String(), nullable=True),
        # Nullable and never zero — zero is not a denominator, it is an unstatable count.
        sa.Column("expected", sa.Integer(), nullable=True),
        sa.Column("observed", sa.Integer(), nullable=False, server_default="0"),
        sa.Column(
            "provider_complete_claim", sa.Boolean(), nullable=False, server_default=sa.false()
        ),
        sa.Column("truncated", sa.Boolean(), nullable=False, server_default=sa.false()),
        sa.Column("run_mode", sa.String(), nullable=True),
        # When the EXTERNAL fact was read, not when this row was written.
        sa.Column("as_of", sa.DateTime(timezone=True), nullable=False),
        sa.Column("created_at", sa.DateTime(timezone=True), nullable=False),
        sa.Column("updated_at", sa.DateTime(timezone=True), nullable=False),
    )
    op.create_index("ix_coverage_reconciliations_run_id", "coverage_reconciliations", ["run_id"])
    op.create_index(
        "ix_coverage_reconciliations_source_id", "coverage_reconciliations", ["source_id"]
    )
    op.create_index(
        "ix_coverage_reconciliations_jurisdiction_id",
        "coverage_reconciliations",
        ["jurisdiction_id"],
    )
    op.create_index("ix_captured_resources_source_id", "captured_resources", ["source_id"])


def downgrade() -> None:
    op.drop_index("ix_captured_resources_source_id", table_name="captured_resources")
    op.drop_index(
        "ix_coverage_reconciliations_jurisdiction_id", table_name="coverage_reconciliations"
    )
    op.drop_index("ix_coverage_reconciliations_source_id", table_name="coverage_reconciliations")
    op.drop_index("ix_coverage_reconciliations_run_id", table_name="coverage_reconciliations")
    op.drop_table("coverage_reconciliations")
