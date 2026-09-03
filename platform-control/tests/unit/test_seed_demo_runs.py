"""The demo-run seeder must produce every lifecycle state, and refuse elsewhere.

The point of the seeder is that a local stack can render the admin's triage UI at
all, so the load-bearing assertion is coverage of :class:`RunStatus` — not the
particular numbers on any one row. The refusal tests matter just as much: a
fixture writer that can be pointed at staging is worse than no fixture writer.
"""

from __future__ import annotations

import os

import pytest
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession, async_sessionmaker

from platform_control.config import get_settings
from platform_control.domain import ExecutionMode, RunStatus
from platform_control.models.authority import Authority, Jurisdiction
from platform_control.models.run import Run
from platform_control.models.source_version import SourceVersion
from platform_control.seed_demo_runs import (
    DEMO_MARKER_KEY,
    DEMO_SOURCE_VERSION_ID,
    DemoSeedRefusedError,
    assert_development_environment,
    seed_demo_runs,
)


async def _seed_reference_data(session_maker: async_sessionmaker[AsyncSession]) -> None:
    """The minimum a demo source can be anchored to."""
    async with session_maker() as session:
        session.add(
            Jurisdiction(
                jurisdiction_id="jur_ch_federal",
                slug="ch",
                name="Switzerland",
                level="federal",
            )
        )
        session.add(
            Authority(
                authority_id="auth_fedlex",
                slug="fedlex",
                name="Fedlex",
                jurisdiction_id="jur_ch_federal",
            )
        )
        await session.commit()


@pytest.mark.asyncio
async def test_seed_covers_every_run_status(
    session_maker: async_sessionmaker[AsyncSession],
) -> None:
    await _seed_reference_data(session_maker)

    summary = await seed_demo_runs(session_maker)

    assert summary.created == len(RunStatus)
    async with session_maker() as session:
        runs = list(await session.scalars(select(Run)))
    # This is the whole point: the local queue can show every state.
    assert {run.status for run in runs} == set(RunStatus)
    assert all(run.run_metadata[DEMO_MARKER_KEY] is True for run in runs)


@pytest.mark.asyncio
async def test_seed_is_idempotent(session_maker: async_sessionmaker[AsyncSession]) -> None:
    await _seed_reference_data(session_maker)

    await seed_demo_runs(session_maker)
    second = await seed_demo_runs(session_maker)

    assert second.created == 0
    assert second.updated == len(RunStatus)
    async with session_maker() as session:
        runs = list(await session.scalars(select(Run)))
    # A seeder that grows the queue on every invocation is not a fixture.
    assert len(runs) == len(RunStatus)


@pytest.mark.asyncio
async def test_pending_run_has_not_started(
    session_maker: async_sessionmaker[AsyncSession],
) -> None:
    await _seed_reference_data(session_maker)
    await seed_demo_runs(session_maker)

    async with session_maker() as session:
        pending = await session.scalar(select(Run).where(Run.status == RunStatus.PENDING))
        running = await session.scalar(select(Run).where(Run.status == RunStatus.RUNNING))

    assert pending is not None
    # `Run.started_at` defaults to now(), so a pending run would otherwise render
    # a duration for work that has not begun.
    assert pending.started_at is None
    assert pending.completed_at is None

    assert running is not None
    assert running.started_at is not None
    assert running.completed_at is None


@pytest.mark.asyncio
async def test_demo_source_version_is_never_live(
    session_maker: async_sessionmaker[AsyncSession],
) -> None:
    await _seed_reference_data(session_maker)
    await seed_demo_runs(session_maker)

    async with session_maker() as session:
        version = await session.get(SourceVersion, DEMO_SOURCE_VERSION_ID)

    assert version is not None
    assert version.execution_mode is ExecutionMode.SHADOW


@pytest.mark.asyncio
async def test_dry_run_persists_nothing(
    session_maker: async_sessionmaker[AsyncSession],
) -> None:
    await _seed_reference_data(session_maker)

    await seed_demo_runs(session_maker, dry_run=True)

    async with session_maker() as session:
        runs = list(await session.scalars(select(Run)))
    assert runs == []


@pytest.mark.asyncio
async def test_seed_refuses_without_reference_data(
    session_maker: async_sessionmaker[AsyncSession],
) -> None:
    with pytest.raises(DemoSeedRefusedError) as excinfo:
        await seed_demo_runs(session_maker)

    assert "seed-reference-data" in str(excinfo.value)


@pytest.mark.parametrize("environment", ["staging", "production"])
def test_refuses_outside_development(monkeypatch: pytest.MonkeyPatch, environment: str) -> None:
    monkeypatch.setitem(os.environ, "PLATFORM_CONTROL_ENVIRONMENT", environment)
    get_settings.cache_clear()
    try:
        with pytest.raises(DemoSeedRefusedError) as excinfo:
            assert_development_environment()
        assert environment in str(excinfo.value)
    finally:
        get_settings.cache_clear()


def test_allows_development(monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setitem(os.environ, "PLATFORM_CONTROL_ENVIRONMENT", "development")
    get_settings.cache_clear()
    try:
        assert_development_environment()
    finally:
        get_settings.cache_clear()
