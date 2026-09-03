"""Seed one run per lifecycle state into a **local development** database.

Why this exists
---------------
Every run a local stack has ever held is ``completed``. The stack gets its runs
from the acceptance loop, and the acceptance loop only leaves a row behind when
it finishes — so ``pending``, ``running``, ``failed`` and ``cancelled`` are
states the admin panel renders and nobody has ever seen. The run queue's triage
affordances (the attention chip, the cancel/retry actions, the failure copy, the
five preset chips) are therefore unreviewable: you cannot look at a screen that
never has anything on it.

That is not a cosmetic gap. The M16 finding that the Runs table hides its
``ACTIONS`` column at 1440px is a finding *about a live run*, and the only lever
an operator has on a live run lives in that column. Reviewing the fix requires a
run that is actually live.

This seeder makes those five states exist. It is a **fixture**, not a
simulation: the rows describe runs that never dispatched anything, and each one
says so in ``metadata.demo_seed``.

Safety
------
Two independent refusals, because a fixture writer pointed at the wrong database
is a data-integrity incident:

1. ``PLATFORM_CONTROL_ENVIRONMENT`` must be ``development``. The setting has no
   default (#683), so "unset" is a startup error rather than a silent
   ``development``.
2. ``--i-know-this-writes-fake-runs`` must be passed, or the CLI refuses. The
   flag is deliberately awkward: there is no accidental invocation of this.

Idempotence
-----------
Run ids are deterministic (``run_demo_pending`` …), so re-running updates the
same five rows instead of growing the queue. The demo source and source version
are likewise fixed ids. Nothing outside the ``*_demo_*`` id space is touched.
"""

from __future__ import annotations

import argparse
import asyncio
from dataclasses import dataclass
from datetime import UTC, datetime, timedelta

from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession, async_sessionmaker

from platform_control.config import get_settings
from platform_control.database import get_session_maker
from platform_control.domain import (
    ExecutionMode,
    RunMode,
    RunStatus,
    SourceStatus,
    SourceVersionStatus,
)
from platform_control.models.authority import Authority, Jurisdiction
from platform_control.models.run import Run
from platform_control.models.source import Source
from platform_control.models.source_version import SourceVersion

DEMO_SOURCE_ID = "src_demo_run_states"
DEMO_SOURCE_VERSION_ID = "sv_demo_run_states"
DEMO_SOURCE_NAME = "Demo · run-state fixtures"

#: Marker written to every row this module creates. Nothing else in the schema
#: carries it, so `metadata->>'demo_seed'` is an exact predicate for "this row is
#: a fixture" — which is what makes the cleanup path safe.
DEMO_MARKER_KEY = "demo_seed"


class DemoSeedRefusedError(RuntimeError):
    """The seeder refused to write. Carries the reason the operator must read."""


@dataclass(frozen=True)
class DemoRunSpec:
    """One row of the fixture queue.

    ``age`` orders the queue so the newest run is the one an operator should
    look at first — the run list sorts by ``created_at DESC``, so the failed run
    leading the queue is what puts the attention chip on a real target.
    """

    suffix: str
    status: RunStatus
    mode: RunMode
    age: timedelta
    artifacts_count: int
    captured_resources_count: int
    failure_reason: str | None
    started: bool
    completed: bool

    @property
    def run_id(self) -> str:
        return f"run_demo_{self.suffix}"


#: The five lifecycle states, newest first. Two of them (`failed`, `running`)
#: are the ones the queue's triage UI is *for*; they lead deliberately.
DEMO_RUN_SPECS: tuple[DemoRunSpec, ...] = (
    DemoRunSpec(
        suffix="failed",
        status=RunStatus.FAILED,
        mode=RunMode.PRODUCTION,
        age=timedelta(minutes=8),
        artifacts_count=0,
        captured_resources_count=2,
        failure_reason=("Demo fixture: provider returned HTTP 503 for 2 of 2 captured resources."),
        started=True,
        completed=True,
    ),
    DemoRunSpec(
        suffix="running",
        status=RunStatus.RUNNING,
        mode=RunMode.PRODUCTION,
        age=timedelta(minutes=21),
        artifacts_count=1,
        captured_resources_count=4,
        failure_reason=None,
        started=True,
        completed=False,
    ),
    DemoRunSpec(
        suffix="pending",
        status=RunStatus.PENDING,
        mode=RunMode.PREVIEW,
        age=timedelta(minutes=34),
        artifacts_count=0,
        captured_resources_count=0,
        failure_reason=None,
        # A pending run has not started. The model defaults `started_at` to
        # now(), which would render a duration for a run that has not begun.
        started=False,
        completed=False,
    ),
    DemoRunSpec(
        suffix="cancelled",
        status=RunStatus.CANCELLED,
        mode=RunMode.PREVIEW,
        age=timedelta(hours=2),
        artifacts_count=0,
        captured_resources_count=1,
        failure_reason="Demo fixture: cancelled by an operator before dispatch completed.",
        started=True,
        completed=True,
    ),
    DemoRunSpec(
        suffix="completed",
        status=RunStatus.COMPLETED,
        mode=RunMode.ACCEPTANCE,
        age=timedelta(hours=5),
        artifacts_count=3,
        captured_resources_count=3,
        failure_reason=None,
        started=True,
        completed=True,
    ),
)


@dataclass
class DemoSeedSummary:
    created: int = 0
    updated: int = 0
    source_created: bool = False
    dry_run: bool = False

    def describe(self) -> str:
        prefix = "Would seed" if self.dry_run else "Seeded"
        source = " (created demo source)" if self.source_created else ""
        return (
            f"{prefix} demo runs: created={self.created} updated={self.updated}"
            f"{source}. States: " + ", ".join(spec.status.value for spec in DEMO_RUN_SPECS)
        )


def assert_development_environment() -> None:
    """Refuse anywhere but a development stack.

    Reading `get_settings()` rather than `os.environ` directly means this shares
    the app's own validation: an unset or misspelled environment is a
    ``ValidationError`` here, not a value this function has to second-guess.
    """
    environment = get_settings().environment
    if environment != "development":
        raise DemoSeedRefusedError(
            f"refusing to write demo runs into a {environment!r} environment. "
            "This seeder writes rows that describe runs which never dispatched; "
            "outside a local stack they would be indistinguishable from real "
            "acquisition history. Set PLATFORM_CONTROL_ENVIRONMENT=development."
        )


async def _ensure_demo_source(session: AsyncSession) -> tuple[SourceVersion, bool]:
    """Return the demo source version, creating it (and its source) if absent.

    Reference data is a prerequisite: a run needs a source, a source needs a
    jurisdiction and an authority, and those come from
    ``platform-control-seed-reference-data``. Rather than invent them here — two
    seeders writing the same tables is how a registry drifts — this refuses and
    names the command to run.
    """
    existing = await session.get(SourceVersion, DEMO_SOURCE_VERSION_ID)
    if existing is not None:
        return existing, False

    jurisdiction = await session.scalar(select(Jurisdiction).limit(1))
    authority = await session.scalar(select(Authority).limit(1))
    if jurisdiction is None or authority is None:
        raise DemoSeedRefusedError(
            "no reference data in this database, so a demo source cannot be "
            "anchored to a jurisdiction and an authority. Run "
            "`platform-control-seed-reference-data` first "
            "(`bash scripts/platform-control-demo.sh seed`)."
        )

    source = await session.get(Source, DEMO_SOURCE_ID)
    if source is None:
        source = Source(
            source_id=DEMO_SOURCE_ID,
            name=DEMO_SOURCE_NAME,
            description=(
                "Local fixture source. Its runs exist so the admin's triage UI has "
                "every lifecycle state to render; none of them dispatched anything."
            ),
            jurisdiction_id=jurisdiction.jurisdiction_id,
            authority_id=authority.authority_id,
            source_type="website",
            status=SourceStatus.ACTIVE,
        )
        session.add(source)

    version = SourceVersion(
        source_version_id=DEMO_SOURCE_VERSION_ID,
        source_id=DEMO_SOURCE_ID,
        version_label="demo-run-states",
        status=SourceVersionStatus.DRAFT,
        # SHADOW, never LIVE: shadow is the repo's word for "wired end to end
        # but fixture-backed, touching no upstream server", which is exactly what
        # these rows describe. `live` here would be the one field that lies.
        execution_mode=ExecutionMode.SHADOW,
        acquisition_spec={"kind": "demo_fixture", "targets": []},
    )
    session.add(version)
    return version, True


def _metadata_for(spec: DemoRunSpec) -> dict:
    return {
        DEMO_MARKER_KEY: True,
        "scope": {"kind": "full_source"},
        "note": (
            f"Seeded by platform-control-seed-demo-runs as the {spec.status.value!r} "
            "example, so the admin run queue has a run in every lifecycle state. "
            "No provider was contacted."
        ),
    }


async def seed_demo_runs(
    session_maker: async_sessionmaker[AsyncSession],
    *,
    dry_run: bool = False,
    now: datetime | None = None,
) -> DemoSeedSummary:
    """Upsert one run per :class:`RunStatus`. Idempotent by construction."""
    reference = now or datetime.now(UTC)
    summary = DemoSeedSummary(dry_run=dry_run)

    async with session_maker() as session:
        _version, summary.source_created = await _ensure_demo_source(session)

        for spec in DEMO_RUN_SPECS:
            created_at = reference - spec.age
            run = await session.get(Run, spec.run_id)
            if run is None:
                run = Run(run_id=spec.run_id)
                session.add(run)
                summary.created += 1
            else:
                summary.updated += 1

            run.source_id = DEMO_SOURCE_ID
            run.source_version_id = DEMO_SOURCE_VERSION_ID
            run.mode = spec.mode
            run.status = spec.status
            run.created_at = created_at
            run.updated_at = created_at
            run.started_at = created_at if spec.started else None
            run.completed_at = created_at + timedelta(minutes=3) if spec.completed else None
            run.artifacts_count = spec.artifacts_count
            run.captured_resources_count = spec.captured_resources_count
            run.failure_reason = spec.failure_reason
            run.run_metadata = _metadata_for(spec)

        # `Run.started_at` carries `default=utcnow`, and a SQLAlchemy column
        # default fires on INSERT whenever the attribute is None — assigning None
        # above is therefore indistinguishable from leaving it unset, and the
        # pending run would be stamped with a start time for work that has not
        # begun. Flushing the INSERTs first, then nulling the column, makes it an
        # UPDATE, where the default does not apply.
        await session.flush()
        for spec in DEMO_RUN_SPECS:
            if spec.started:
                continue
            run = await session.get(Run, spec.run_id)
            if run is not None:
                run.started_at = None
        await session.flush()

        if dry_run:
            await session.rollback()
        else:
            await session.commit()

    return summary


def parse_args(argv: list[str] | None = None) -> argparse.Namespace:
    parser = argparse.ArgumentParser(
        description=(
            "Seed one platform-control run per lifecycle state into a LOCAL "
            "development database, so the admin run queue can be reviewed with "
            "pending / running / failed / cancelled rows present."
        )
    )
    parser.add_argument(
        "--i-know-this-writes-fake-runs",
        action="store_true",
        help=(
            "Required. These rows describe runs that never dispatched; the flag "
            "exists so nobody reaches this state by tab-completion."
        ),
    )
    parser.add_argument(
        "--dry-run",
        action="store_true",
        help="Report what would be written without committing it.",
    )
    return parser.parse_args(argv)


def main(argv: list[str] | None = None) -> None:
    args = parse_args(argv)
    if not args.i_know_this_writes_fake_runs:
        raise SystemExit(
            "refusing to run without --i-know-this-writes-fake-runs. This seeder "
            "writes rows that describe runs which never dispatched."
        )
    assert_development_environment()
    summary = asyncio.run(seed_demo_runs(get_session_maker(), dry_run=args.dry_run))
    print(summary.describe())


if __name__ == "__main__":
    main()
