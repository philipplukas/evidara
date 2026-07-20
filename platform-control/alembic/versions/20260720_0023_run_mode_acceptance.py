"""Add 'acceptance' to the run_mode enum — the ADR-0030 evidence run (#743).

`RunMode.ACCEPTANCE` is the operator's one-shot rehearsal against a live portal:
the run that *produces* the evidence for turning the ADR-0030 keys, and the only
way an AWAITING_EVIDENCE provider can earn its first key without an engineer.

WHY A MIGRATION IS NEEDED AND WHY NO TEST CAUGHT ITS ABSENCE
------------------------------------------------------------
`runs.mode` is a **native PostgreSQL enum**: the initial schema created it as
`sa.Enum("preview", "production", name="run_mode")` (20260329_0001:122), and
`sa.Enum` defaults to `native_enum=True`. Postgres will reject any value outside
the type's labels, so without this migration every acceptance run fails on
INSERT with `invalid input value for enum run_mode: "acceptance"` — including
the refusal path, since `_record_refused_run` also inserts a Run row. The
operator would follow the remedy the admin itself prints and get a 500.

The model (`models/run.py`) declares `native_enum=False`, so it renders a plain
VARCHAR. Every test builds the schema with `Base.metadata.create_all` against
SQLite (`tests/conftest.py`), and both Testcontainers-Postgres suites do the
same — so 'acceptance' inserts fine everywhere in CI and nothing meets the
Alembic-built schema this migration corrects.

That is the two-producers-of-one-schema hazard AGENTS.md records from #675/#713,
in a new place: the migration and the model both define `runs.mode`, and the one
CI exercises is not the one production uses. Any future change to an enum-typed
column needs a migration even though the model-built test schema will not
complain.

`ALTER TYPE ... ADD VALUE` cannot run inside a transaction block on PostgreSQL
older than 12; it is also not reversible — Postgres has no `DROP VALUE`. The
downgrade is therefore a documented no-op rather than a lie.

Revision ID: 20260720_0023
Revises: 20260717_0022
Create Date: 2026-07-20
"""

from alembic import op

revision = "20260720_0023"
down_revision = "20260717_0022"
branch_labels = None
depends_on = None


def upgrade() -> None:
    bind = op.get_bind()
    if bind.dialect.name != "postgresql":
        # SQLite (tests) stores the column as TEXT and has no enum type to alter.
        return
    # IF NOT EXISTS makes this safe to re-run and safe on a database whose type
    # was created from the model rather than from the initial migration.
    op.execute("ALTER TYPE run_mode ADD VALUE IF NOT EXISTS 'acceptance'")


def downgrade() -> None:
    """No-op: PostgreSQL cannot remove a value from an enum type.

    Reversing this properly means recreating the type without the label and
    rewriting every dependent column, which would fail anyway while any row
    still carries `mode = 'acceptance'`. Leaving the label in place is harmless:
    nothing writes it unless the application asks for an acceptance run.
    """
