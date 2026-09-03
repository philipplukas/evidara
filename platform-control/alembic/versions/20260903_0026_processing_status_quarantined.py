"""Add 'quarantined' to the processing_status enum — ADR-0047's refusal (#731).

`ProcessingStatus.QUARANTINED` is document-intelligence saying a structurally
valid manifestation is not law: a scan with no text layer, a cover sheet, an empty
text layer. #841 implements the judgment; without this label platform-control
cannot store the event, so the operator's run view shows `accepted → processing`
and then simply stops. A run that *refused* is indistinguishable from one that
hung — which is precisely the silence ADR-0047 exists to end.

WHY A MIGRATION IS NEEDED, AND WHY NO TEST WILL CATCH ITS ABSENCE
------------------------------------------------------------------
`processing_status_updates.status` is a **native PostgreSQL enum**: the initial
read-model migration created it as `sa.Enum("accepted", …, name="processing_status")`
(20260402_0002:28-38), and `sa.Enum` defaults to `native_enum=True`. Postgres
rejects any label outside the type, so without this every quarantine event fails
on INSERT with `invalid input value for enum processing_status: "quarantined"`.

The model (`models/processing_status_update.py:20-27`) declares
`native_enum=False`, so it renders a plain VARCHAR — and every test builds the
schema from the model with `Base.metadata.create_all`, including both
Testcontainers-Postgres suites. So `quarantined` inserts happily everywhere in CI
and nothing ever meets the Alembic-built schema this migration corrects.

That is the same two-producers-of-one-schema hazard recorded in AGENTS.md from
#675/#713 and hit again in 20260720_0023: the migration and the model both define
this column, and the one CI exercises is not the one production uses. Any future
change to an enum-typed column needs a migration even though the whole suite will
stay green without it.

TRANSACTIONS, AND WHY THERE IS NO `autocommit_block()` HERE
------------------------------------------------------------
`ALTER TYPE … ADD VALUE` cannot run inside a transaction block on PostgreSQL
**older than 12**. Since 12 it can — the restriction that remains is that the new
label cannot be *used* in the same transaction that adds it, which this migration
does not do. This repo targets 16 (`PostgresContainer("postgres:16-alpine")` in
both integration suites) and 20260720_0023 already relies on exactly this for
`run_mode`. Following that precedent rather than inventing a second pattern: an
`autocommit_block()` here would buy nothing and would forfeit the migration's
atomicity.

IRREVERSIBLE, SAID OUT LOUD
---------------------------
PostgreSQL has no `DROP VALUE`. `downgrade()` is a documented no-op, not a stub
that silently pretends — see its docstring.

Revision ID: 20260903_0026
Revises: 20260903_0025
Create Date: 2026-09-03
"""

from alembic import op

revision = "20260903_0026"
down_revision = "20260903_0025"
branch_labels = None
depends_on = None


def upgrade() -> None:
    bind = op.get_bind()
    if bind.dialect.name != "postgresql":
        # SQLite (tests) stores the column as TEXT and has no enum type to alter.
        return
    # IF NOT EXISTS makes this safe to re-run and safe on a database whose type
    # was created from the model rather than from the initial migration.
    op.execute("ALTER TYPE processing_status ADD VALUE IF NOT EXISTS 'quarantined'")


def downgrade() -> None:
    """No-op: PostgreSQL cannot remove a value from an enum type.

    There is no `ALTER TYPE … DROP VALUE`. Reversing this properly means creating
    a replacement type without the label, rewriting every dependent column to it,
    and dropping the old one — which fails anyway while any row still carries
    `status = 'quarantined'`, and those rows are the record of documents the
    corpus deliberately does not hold. Leaving the label in place is harmless:
    nothing writes it unless document-intelligence quarantines something.

    Deliberately not `raise NotImplementedError`: that would block a downgrade
    past this revision for a migration whose forward effect is inert, which is a
    worse failure mode than an honest no-op. The two behaviours are the same
    here — the label stays either way — so the difference is only whether an
    operator can step back through it.
    """
