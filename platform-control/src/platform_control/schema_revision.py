"""Does the database's schema match the code that is about to write to it?

Nothing asked this before, and on 2026-09-06 that cost us. A pin bump rolled the
API to a commit that emits `ProcessingStatus.QUARANTINED` while the database was
still one Alembic revision behind. The pod came up, passed its readiness probe
(which was `SELECT 1`), and served traffic. The mismatch would have surfaced only
when some run actually tried to write `quarantined` and Postgres rejected the
value — an operator-visible refusal turning into an invisible one, which is the
exact silence ADR-0047 exists to end.

`0026`'s own docstring names why no test caught it: `processing_status_updates.status`
is a **native** Postgres enum in the migration but `native_enum=False` on the
model, and every suite builds its schema with `Base.metadata.create_all` from the
model. So CI never meets the Alembic-built schema at all.

This module makes the mismatch *visible* rather than latent. It does not prevent
it — that is the `PreSync` hook's job (ADR-0055) — it ensures that when ordering
fails anyway, the pod says so instead of quietly serving.

## Three outcomes, deliberately, not two

`MATCH`, `MISMATCH` and `UNKNOWN` are different answers and are reported as such.
Collapsing `UNKNOWN` into either one is what turns a check into decoration:

  - **MATCH** — the DB's `alembic_version` equals the code's head.
  - **MISMATCH** — they differ. Both revisions are named, so an operator does not
    have to go and look them up.
  - **UNKNOWN** — there is no `alembic_version` table, or the migration scripts
    are not on disk. Legitimate in tests (schema built by `create_all`) and in a
    local run from a checkout without the alembic tree. Reported, never asserted.

Only `MISMATCH` degrades readiness. `UNKNOWN` is surfaced in the body so an
operator can see that the question went unanswered — a check that silently
abstains is the failure mode this repo keeps rediscovering (ADR-0051).
"""

from __future__ import annotations

from dataclasses import dataclass
from enum import StrEnum
from functools import lru_cache
from pathlib import Path

from sqlalchemy import text
from sqlalchemy.ext.asyncio import AsyncSession


class SchemaRevisionStatus(StrEnum):
    MATCH = "match"
    MISMATCH = "mismatch"
    UNKNOWN = "unknown"


@dataclass(frozen=True)
class SchemaRevision:
    status: SchemaRevisionStatus
    """Revision the code expects, or `None` when the scripts were not found."""
    expected: str | None
    """Revision the database reports, or `None` when there is no version table."""
    actual: str | None
    detail: str


def _candidate_script_dirs() -> list[Path]:
    """Places `alembic/versions` can legitimately live.

    The package is pip-installed into site-packages while the migration scripts
    are copied to the image's WORKDIR (`/app`), so `platform_control.__file__`
    does NOT locate them. Both layouts are checked rather than assuming one:
    guessing wrong would report UNKNOWN in production, which is the answer that
    hides the problem this module exists to expose.
    """
    here = Path(__file__).resolve()
    return [
        # Container: WORKDIR /app, `COPY platform-control/ /app/`.
        Path.cwd() / "alembic" / "versions",
        # Editable / source checkout: src/platform_control/… → platform-control/.
        here.parents[2] / "alembic" / "versions",
        here.parents[3] / "alembic" / "versions",
    ]


@lru_cache(maxsize=1)
def expected_head() -> str | None:
    """The single head revision the shipped migration scripts define.

    Read by parsing `revision`/`down_revision` out of the version files rather
    than by booting Alembic's `ScriptDirectory`, which wants an `alembic.ini`,
    a configured `sqlalchemy.url`, and imports `env.py` — none of which a
    readiness probe should be doing on every call.

    Returns `None` when the scripts are absent, or when the graph does not have
    exactly one head. A branched graph is a real condition and must not be
    silently reduced to "some head".
    """
    versions_dir = next((d for d in _candidate_script_dirs() if d.is_dir()), None)
    if versions_dir is None:
        return None

    revisions: set[str] = set()
    parents: set[str] = set()
    for script in versions_dir.glob("*.py"):
        for line in script.read_text(encoding="utf-8").splitlines():
            stripped = line.strip()
            # `revision = "x"` / `down_revision = "y"`, quoted either way.
            if stripped.startswith("revision ="):
                revisions.add(stripped.split("=", 1)[1].strip().strip("\"'"))
            elif stripped.startswith("down_revision ="):
                value = stripped.split("=", 1)[1].strip().strip("\"'")
                if value != "None":
                    parents.add(value)

    heads = revisions - parents
    return heads.pop() if len(heads) == 1 else None


async def read_schema_revision(session: AsyncSession) -> SchemaRevision:
    """Compare the database's Alembic revision to the code's head."""
    expected = expected_head()

    try:
        result = await session.execute(text("SELECT version_num FROM alembic_version"))
        actual = result.scalar()
    except Exception:
        # No `alembic_version` table: a schema built by `create_all` (every test
        # suite) or a database that has never been migrated. Not assertable.
        return SchemaRevision(
            status=SchemaRevisionStatus.UNKNOWN,
            expected=expected,
            actual=None,
            detail=(
                "no alembic_version table — schema was not built by Alembic "
                "(normal under create_all; in a deployed environment it means "
                "the migrate job has never run)"
            ),
        )

    if expected is None:
        return SchemaRevision(
            status=SchemaRevisionStatus.UNKNOWN,
            expected=None,
            actual=actual,
            detail=(
                "migration scripts not found on disk, or the revision graph has "
                "no single head — cannot say what this code expects"
            ),
        )

    if actual == expected:
        return SchemaRevision(
            status=SchemaRevisionStatus.MATCH,
            expected=expected,
            actual=actual,
            detail=f"schema at {actual}",
        )

    return SchemaRevision(
        status=SchemaRevisionStatus.MISMATCH,
        expected=expected,
        actual=actual,
        detail=(
            f"database is at {actual}, this code expects {expected}. "
            "Writes that depend on the newer schema will fail at the statement, "
            "not at startup. Run the migrate job before serving."
        ),
    )
