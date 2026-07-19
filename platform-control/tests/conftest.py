from __future__ import annotations

import os
from collections.abc import AsyncIterator
from pathlib import Path
from tempfile import TemporaryDirectory

import pytest
import pytest_asyncio
from ci_skip_guard import CiSkipGuard
from sqlalchemy.ext.asyncio import AsyncSession, async_sessionmaker, create_async_engine
from temporalio.testing import WorkflowEnvironment

from platform_control import models as _models  # noqa: F401
from platform_control.config import get_settings
from platform_control.database import reset_database_caches
from platform_control.models.base import Base

# Auth fails closed when no API key is configured (see `platform_control.auth`).
# The suite runs keyless by design, so it opts into the local-development open path
# by name — the same way `docker-compose.local.yml` does. `setdefault` so a test that
# wants to exercise the fail-closed branch can override it via monkeypatch/env.
# This must run before any `Settings()` is constructed, hence module import time.
os.environ.setdefault("PLATFORM_CONTROL_AUTH_DEV_ALLOW_UNAUTHENTICATED", "1")

# `Settings.environment` is required and has no default (#683) — the suite must declare
# which environment it is, the same as any deployment. `setdefault` so a test can override.
os.environ.setdefault("PLATFORM_CONTROL_ENVIRONMENT", "development")

# Where the temporalio SDK caches the `temporal-test-server` binary it drives
# `WorkflowEnvironment.start_time_skipping()` with. The binary is fetched once
# per SDK version and reused forever after; the server itself is local (it binds
# a loopback port and talks to nothing). Keeping the cache inside the repo — and
# not in the system temp dir the SDK defaults to — is what lets CI restore it
# from `actions/cache` instead of re-fetching ~80MB on every run.
TEMPORAL_TEST_SERVER_DIR = Path(
    os.environ.get(
        "TEMPORAL_TEST_SERVER_DIR",
        Path(__file__).resolve().parent.parent / ".temporal-test-server",
    )
)


def pytest_configure(config: pytest.Config) -> None:
    """Register the "CI may not skip" guard (#690).

    Generalises the per-site rule below to every skip in the suite: in CI, a
    skipped test fails the run unless its reason is allowlisted. See
    tests/ci_skip_guard.py for the rationale and the allowlist.
    """
    config.pluginmanager.register(CiSkipGuard(), "ci-skip-guard")


def pytest_collection_modifyitems(config: pytest.Config, items: list[pytest.Item]) -> None:
    """Opt *out* of `temporal` tests with PYTEST_SKIP_TEMPORAL=1 — they run by default.

    These tests used to carry `requires_network` and were skipped unless
    `PYTEST_NETWORK_TESTS=1`, which no CI job ever set — so every test that
    started a Temporal workflow was skipped on every CI run (#564). The marker
    was also a misnomer: `start_time_skipping()` runs a *local* test server. It
    only touches the network to fetch that server's binary the first time, and
    CI now caches it (see TEMPORAL_TEST_SERVER_DIR above).

    So the default is inverted: marked tests run. The escape hatch exists for
    genuinely offline machines with a cold binary cache, and CI is not allowed
    to use it — otherwise we would silently drift back to zero executing
    Temporal tests, which is exactly how the integration rotted.

    Note the `Replayer` tests are deliberately *not* marked: replay is pure and
    in-process, so it needs neither the binary nor a server, and guards workflow
    determinism on every run regardless of environment.

    See: docs/runbooks/pytest-temporal-marker.md.
    """
    if os.environ.get("PYTEST_SKIP_TEMPORAL") != "1":
        return
    if os.environ.get("CI"):
        raise pytest.UsageError(
            "PYTEST_SKIP_TEMPORAL=1 is not honoured in CI: the Temporal integration is "
            "kept but switched off (ADR-0031), so these tests are the only thing keeping "
            "it from rotting. Cache the test-server binary instead of skipping (#564)."
        )
    skip_marker = pytest.mark.skip(
        reason="PYTEST_SKIP_TEMPORAL=1; unset it to run the Temporal test server"
    )
    for item in items:
        if "temporal" in item.keywords:
            item.add_marker(skip_marker)


@pytest_asyncio.fixture
async def temporal_env() -> AsyncIterator[WorkflowEnvironment]:
    """A time-skipping Temporal environment backed by the cached local test server.

    Every test that drives a real workflow should take this fixture rather than
    calling `WorkflowEnvironment.start_time_skipping()` directly, so the binary
    cache location stays in one place.
    """
    TEMPORAL_TEST_SERVER_DIR.mkdir(parents=True, exist_ok=True)
    async with await WorkflowEnvironment.start_time_skipping(
        download_dest_dir=str(TEMPORAL_TEST_SERVER_DIR),
    ) as env:
        yield env


@pytest_asyncio.fixture
async def session_maker() -> AsyncIterator[async_sessionmaker[AsyncSession]]:
    previous_env = {
        "PLATFORM_CONTROL_DATABASE_URL": os.environ.get("PLATFORM_CONTROL_DATABASE_URL"),
        "PLATFORM_CONTROL_FIRECRAWL_WEBHOOK_SECRET": os.environ.get(
            "PLATFORM_CONTROL_FIRECRAWL_WEBHOOK_SECRET"
        ),
        "PLATFORM_CONTROL_RAW_ARTIFACT_LOCAL_DIR": os.environ.get(
            "PLATFORM_CONTROL_RAW_ARTIFACT_LOCAL_DIR"
        ),
    }

    with TemporaryDirectory() as tmpdir:
        db_path = Path(tmpdir) / "test.db"
        raw_dir = Path(tmpdir) / "artifacts"
        os.environ["PLATFORM_CONTROL_DATABASE_URL"] = f"sqlite+aiosqlite:///{db_path}"
        os.environ["PLATFORM_CONTROL_FIRECRAWL_WEBHOOK_SECRET"] = "test-secret"
        os.environ["PLATFORM_CONTROL_RAW_ARTIFACT_LOCAL_DIR"] = str(raw_dir)
        get_settings.cache_clear()
        reset_database_caches()

        engine = create_async_engine(os.environ["PLATFORM_CONTROL_DATABASE_URL"])
        async with engine.begin() as connection:
            await connection.run_sync(Base.metadata.create_all)

        yield async_sessionmaker(engine, expire_on_commit=False)

        await engine.dispose()

    for key, value in previous_env.items():
        if value is None:
            os.environ.pop(key, None)
        else:
            os.environ[key] = value

    get_settings.cache_clear()
    reset_database_caches()


@pytest_asyncio.fixture
async def session(session_maker: async_sessionmaker[AsyncSession]) -> AsyncIterator[AsyncSession]:
    async with session_maker() as active_session:
        yield active_session
