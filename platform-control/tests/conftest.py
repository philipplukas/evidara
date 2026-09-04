from __future__ import annotations

import os
import sys
from collections.abc import AsyncIterator
from pathlib import Path
from tempfile import TemporaryDirectory

import pytest
import pytest_asyncio
from sqlalchemy.ext.asyncio import AsyncSession, async_sessionmaker, create_async_engine
from temporalio.testing import WorkflowEnvironment

from platform_control import models as _models  # noqa: F401
from platform_control.config import get_settings
from platform_control.database import reset_database_caches
from platform_control.domain import RobotsMode
from platform_control.models.base import Base
from platform_control.models.compliance_policy import CompliancePolicy

# The "CI may not skip" guard is shared across platform-control, document-intelligence
# and eval (#690). These are three separate Python projects with no common package, so
# the one implementation lives in the repo's shared entry point, `scripts/`.
sys.path.insert(0, str(Path(__file__).resolve().parents[2] / "scripts"))

from ci_skip_guard import CiSkipGuard  # noqa: E402

# Substrings of skip reasons that are legitimate in CI, each with the reason it is
# excused. Empty today, and that is the honest state: a full run of this suite is
# `547 passed, 0 skipped` (#690). Nothing here is optional, so nothing is excused.
# Adding an entry requires saying why, here:
ALLOWED_SKIPS: dict[str, str] = {
    # "requires a live LLM": "DI_EVAL_LIVE evals cost money and need a key.",
}

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
    scripts/ci_skip_guard.py for the rationale, and ALLOWED_SKIPS above for the
    (currently empty) list of skips this suite excuses.
    """
    config.pluginmanager.register(CiSkipGuard(ALLOWED_SKIPS), "ci-skip-guard")


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


def dispatchable_compliance_policy(
    *,
    compliance_policy_id: str = "cp_test",
    name: str = "test-politeness",
) -> CompliancePolicy:
    """A minimal policy so a seeded jurisdiction can actually dispatch a run.

    A source whose jurisdiction resolves to no ``CompliancePolicy`` is refused at
    dispatch (``compliance_policy_missing``) rather than running unpaced and
    robots-blind. Before that refusal existed, **every** dispatch test in this
    suite ran without a policy — which is the same hole the seed tree had, and
    is why nobody noticed the production one.

    So this is not boilerplate to satisfy a new check: a test that dispatches
    without one is rehearsing a run that must not happen. Attach it with::

        policy = dispatchable_compliance_policy()
        session.add(policy)
        session.add(Jurisdiction(..., compliance_policy_id=policy.compliance_policy_id))

    ``robots_mode`` is STRICT here on purpose — the safe default a real policy
    gets — so tests exercise the enforcing branch rather than the exempt one.
    """
    return CompliancePolicy(
        compliance_policy_id=compliance_policy_id,
        name=name,
        robots_mode=RobotsMode.STRICT,
        max_requests_per_minute_per_host=60,
        max_concurrent_per_host=2,
    )


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
