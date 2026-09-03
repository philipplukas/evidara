"""Make the Temporal shard crawl idempotent and its progress writes lossless (#561).

Two columns, one per half of #561.

`runs.idempotency_key` — ATTEMPT-INVARIANT RUN CREATION
-------------------------------------------------------
`ScopeShardWorkflow` retries `run_shard_crawl` up to five times
(`temporal/workflows.py`), and the activity created a fresh `Run` row and
re-dispatched the provider on every attempt. One transient error therefore meant
up to five duplicate rows and five full re-scrapes of the *same shard* of a
government legal portal. The dedupe key is `wizard:<wizard_run_id>:shard:<key>`,
and the UNIQUE index is the thing that actually enforces it: `INSERT … ON
CONFLICT DO NOTHING RETURNING run_id` returns a row only to the attempt that
created it, so a retry provably cannot dispatch a second time. A "does a run
already exist?" SELECT would have left a race window as wide as the bug.

NULL for every other run, and deliberately so — an operator who presses "run"
twice means it twice. Only callers retried by machinery set it. Multiple NULLs
coexist under a UNIQUE index on both Postgres and SQLite.

`wizard_runs.progress_version` — LOSSLESS PROGRESS WRITES
---------------------------------------------------------
Shards fan out through `asyncio.gather` and update the `progress` JSON column
concurrently. Every writer did a read-modify-write with nothing between the
read and the write, so two shards finishing at once silently discarded one
another's entry and its contribution to the aggregate counters. This column
carries an optimistic-concurrency version: writers go through
`services/wizard_progress.py`, whose `UPDATE … WHERE progress_version = :v`
commits only if nobody else did, and re-applies the mutation when it did not.

A version column rather than `SELECT … FOR UPDATE` because the test suite runs
on SQLite, where SQLAlchemy emits no `FOR UPDATE` clause at all — a lock-based
fix would be untested by the very tests claiming to prove it.

ROLLOUT
-------
Both columns are additive and backfill-free: `idempotency_key` is nullable and
`progress_version` has `server_default '0'`, so existing rows are valid the
moment the DDL lands and old application code keeps working against the new
schema. No staged rollout in the sense of #253 is required — but note the
ordering that always applies: migrate first, deploy second. Old code inserting
into `runs` without `idempotency_key` writes NULL, which the UNIQUE index
permits.

There is nothing to backfill for the wizard: `PLATFORM_CONTROL_WIZARD_ORCHESTRATOR_BACKEND`
is `in_memory` in every environment and no Temporal server is deployed
(ADR-0031), so no shard run has ever written this progress.

Note for whoever changes this next: `tests/conftest.py` builds the schema with
`Base.metadata.create_all` against SQLite, so a model without a migration passes
the entire suite and fails only in production. Nothing in CI compares the two.
Verify by hand with `alembic upgrade head` against a real Postgres.

Revision ID: 20260903_0025
Revises: 20260728_0024
Create Date: 2026-09-03
"""

import sqlalchemy as sa

from alembic import op

revision = "20260903_0025"
down_revision = "20260728_0024"
branch_labels = None
depends_on = None


def upgrade() -> None:
    op.add_column("runs", sa.Column("idempotency_key", sa.String(), nullable=True))
    # A UNIQUE *index* rather than a UNIQUE constraint: SQLite cannot ALTER TABLE
    # ADD CONSTRAINT, and the index enforces exactly the same thing on both engines.
    op.create_index(
        "uq_runs_idempotency_key",
        "runs",
        ["idempotency_key"],
        unique=True,
    )
    op.add_column(
        "wizard_runs",
        sa.Column("progress_version", sa.Integer(), nullable=False, server_default="0"),
    )


def downgrade() -> None:
    op.drop_column("wizard_runs", "progress_version")
    op.drop_index("uq_runs_idempotency_key", table_name="runs")
    op.drop_column("runs", "idempotency_key")
