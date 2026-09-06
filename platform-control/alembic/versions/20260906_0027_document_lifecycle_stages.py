"""Add `document_lifecycle_events.stages` — per-stage DI timings (#905).

document-intelligence now records what each pipeline stage did for a document
(`normalize`, `sectionize`, `extract`, `assemble`, `enrich`, `finalize`: duration
and in/out counts) and denormalises it onto `document.processed`. This column is
where the control plane keeps it, so the run detail can render a stage timeline
without reading the lakehouse.

NULLABLE, AND NULL IS NOT `[]`
------------------------------
The column is nullable with no server default, and that is load-bearing rather
than convenience:

* **NULL** — this row carries no ledger. Every row written before this migration
  is NULL, and so is every row from a producer that emits no stages. The honest
  rendering is "not recorded".
* **`[]`** — a producer sent an empty ledger, i.e. a claim that the pipeline ran
  no stages.

Backfilling NULL to `[]` would convert "we never recorded this" into "nothing
happened", which is the silent-zero failure this repo keeps paying for (#605,
#675, #713, and ADR-0044's whole subject). So there is no backfill, and every
reader must distinguish the two.

WHY THIS IS A PLAIN `JSON` COLUMN
---------------------------------
`JSONB` would be the better Postgres choice for querying, but nothing queries
*inside* the ledger — the run detail reads the whole array for one row and
renders it. Matching the model's `sa.JSON` keeps the Alembic-built schema and the
`Base.metadata.create_all` schema that every test builds from identical. That
divergence is exactly the two-producers-of-one-schema hazard recorded in
AGENTS.md (#675/#713) and hit again in 20260720_0023 and 20260903_0026: when the
migration and the model disagree, CI exercises the model and production runs the
migration. Choosing `JSONB` here for a query nobody makes would reintroduce it.

Additive and reversible: no existing row changes, and the downgrade drops a
column nothing else references.
"""

from __future__ import annotations

import sqlalchemy as sa

from alembic import op

revision = "20260906_0027"
down_revision = "20260903_0026"
branch_labels = None
depends_on = None


def upgrade() -> None:
    op.add_column(
        "document_lifecycle_events",
        sa.Column("stages", sa.JSON(), nullable=True),
    )


def downgrade() -> None:
    op.drop_column("document_lifecycle_events", "stages")
