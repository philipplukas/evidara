"""Progress writes against real Postgres, with real concurrency (#561).

`tests/unit/test_wizard_progress_store.py` proves the compare-and-set is correct
by interleaving deterministically on SQLite. That is the test that fails when the
guard is removed, and it is the one to read first.

This is the other half: many writers, genuinely at once, on the engine
platform-control actually deploys against. It is here rather than in the unit
suite because SQLite serializes writers at the file level, so a unit test cannot
demonstrate that the version predicate — and not the engine — is what makes the
outcome correct. On Postgres the sessions really do overlap.
"""

from __future__ import annotations

import asyncio
from collections.abc import AsyncIterator

import pytest
import pytest_asyncio
from docker.errors import DockerException
from sqlalchemy.ext.asyncio import AsyncSession, async_sessionmaker, create_async_engine
from testcontainers.core.exceptions import ContainerStartException
from testcontainers.postgres import PostgresContainer

from platform_control import models as _models  # noqa: F401
from platform_control.models.base import Base
from platform_control.models.wizard_project import WizardProject
from platform_control.models.wizard_run import WizardRun
from platform_control.services.wizard_progress import (
    roll_up_shard_totals,
    update_wizard_progress,
)
from platform_control.temporal.activities import ScopeShardActivities

SHARD_COUNT = 12


def _to_asyncpg_url(url: str) -> str:
    if url.startswith("postgresql+psycopg://"):
        return url.replace("postgresql+psycopg://", "postgresql+asyncpg://", 1)
    if url.startswith("postgresql://"):
        return url.replace("postgresql://", "postgresql+asyncpg://", 1)
    return url


@pytest_asyncio.fixture
async def postgres_session_maker() -> AsyncIterator[async_sessionmaker[AsyncSession]]:
    try:
        with PostgresContainer("postgres:16-alpine", driver="psycopg") as postgres:
            engine = create_async_engine(_to_asyncpg_url(postgres.get_connection_url()))
            async with engine.begin() as connection:
                await connection.run_sync(Base.metadata.create_all)

            yield async_sessionmaker(engine, expire_on_commit=False)

            await engine.dispose()
    except (ContainerStartException, DockerException, OSError) as exc:
        pytest.skip(f"Docker-backed Postgres is unavailable: {exc}")


async def _seed_wizard_run(session_maker: async_sessionmaker[AsyncSession]) -> str:
    async with session_maker() as session:
        project = WizardProject(name="concurrent shards")
        session.add(project)
        await session.flush()
        run = WizardRun(wizard_project_id=project.wizard_project_id, progress={})
        session.add(run)
        await session.commit()
        return run.wizard_run_id


@pytest.mark.asyncio
async def test_concurrent_shard_reports_all_land_on_postgres(postgres_session_maker) -> None:
    """Every shard's completion survives, and the aggregates match the parts.

    This is the admin-UI bug from #561 stated as an assertion: with a
    read-modify-write, shards finishing near-simultaneously silently overwrote
    each other and the counters came out low, with nothing logged.
    """
    wizard_run_id = await _seed_wizard_run(postgres_session_maker)
    shard_acts = ScopeShardActivities(session_factory=postgres_session_maker)
    stats = {"nodes_discovered": 7, "records_accepted": 5, "records_sent_to_review": 2}

    await asyncio.gather(
        *[
            shard_acts.report_shard_progress(wizard_run_id, f"shard-{index}", stats)
            for index in range(SHARD_COUNT)
        ]
    )

    async with postgres_session_maker() as session:
        run = await session.get(WizardRun, wizard_run_id)
        assert run is not None
        assert len(run.progress["shards"]) == SHARD_COUNT
        assert run.progress["total_nodes"] == 7 * SHARD_COUNT
        assert run.progress["accepted_records"] == 5 * SHARD_COUNT
        assert run.progress["routed_to_review"] == 2 * SHARD_COUNT
        # One committed version bump per writer: nobody's write was skipped, and
        # nobody's write was applied twice.
        assert run.progress_version == SHARD_COUNT


@pytest.mark.asyncio
async def test_concurrent_writers_to_the_same_shard_key_converge(postgres_session_maker) -> None:
    """Same key from several writers is last-write-wins, not a corrupted aggregate.

    A retried activity racing its own earlier attempt must not leave the derived
    counters counting the shard twice — the totals are recomputed from the shard
    entries on every write, so the end state is the same whichever writer lands last.
    """
    wizard_run_id = await _seed_wizard_run(postgres_session_maker)

    def write_same_shard(progress: dict) -> dict:
        shards = dict(progress.get("shards") or {})
        shards["ch/zurich"] = {"records_accepted": 4, "nodes_discovered": 4}
        progress["shards"] = shards
        return roll_up_shard_totals(progress)

    await asyncio.gather(
        *[
            update_wizard_progress(postgres_session_maker, wizard_run_id, write_same_shard)
            for _ in range(SHARD_COUNT)
        ]
    )

    async with postgres_session_maker() as session:
        run = await session.get(WizardRun, wizard_run_id)
        assert run is not None
        assert list(run.progress["shards"]) == ["ch/zurich"]
        assert run.progress["accepted_records"] == 4
        assert run.progress["total_nodes"] == 4
