from __future__ import annotations

import pytest

from platform_control.cli.plan import format_plan, resolve_plan
from platform_control.domain import ExecutionMode
from platform_control.errors import NotFoundError
from platform_control.models.authority import Authority, Jurisdiction
from platform_control.models.source import Source
from platform_control.models.source_version import SourceVersion
from platform_control.services.deterministic_http_provider import DeterministicHttpProvider
from platform_control.services.firecrawl_provider import FirecrawlProvider
from platform_control.services.provider_registry import ProviderRegistry


class _StubSettings:
    firecrawl_api_key = None
    firecrawl_base_url = "https://api.firecrawl.dev"
    firecrawl_webhook_url = None


def _build_registry() -> ProviderRegistry:
    registry = ProviderRegistry()
    registry.register(FirecrawlProvider(_StubSettings()))
    registry.register(DeterministicHttpProvider())
    return registry


async def _seed(session, *, spec: dict, execution_mode: ExecutionMode = ExecutionMode.LIVE) -> str:
    session.add(Jurisdiction(jurisdiction_id="jur_ch", name="Switzerland", slug="ch"))
    session.add(
        Authority(
            authority_id="auth_zh_admin",
            jurisdiction_id="jur_ch",
            name="Zurich Administrative Court",
            slug="zh-admin-court",
        )
    )
    await session.flush()

    source = Source(
        name="Zurich decisions",
        jurisdiction_id="jur_ch",
        authority_id="auth_zh_admin",
    )
    session.add(source)
    await session.flush()

    version = SourceVersion(
        source_id=source.source_id,
        version_label="v1",
        execution_mode=execution_mode,
        acquisition_spec=spec,
    )
    session.add(version)
    await session.commit()
    return version.source_version_id


@pytest.mark.asyncio
async def test_resolve_plan_returns_firecrawl_plan(session) -> None:
    source_version_id = await _seed(
        session,
        spec={
            "provider": "firecrawl",
            "mode": "crawl",
            "seed_url": "https://example.com/decisions",
            "limit": 42,
            "max_discovery_depth": 3,
            "include_paths": ["/decisions/"],
            "exclude_paths": ["/drafts/"],
        },
    )

    _, _, plan = await resolve_plan(session, _build_registry(), source_version_id)

    assert plan.provider == "firecrawl"
    assert plan.mode == "crawl"
    assert plan.seed_urls == ["https://example.com/decisions"]
    assert plan.estimated_request_count == 42
    assert plan.max_discovery_depth == 3
    assert plan.include_paths == ["/decisions/"]
    assert plan.exclude_paths == ["/drafts/"]


@pytest.mark.asyncio
async def test_resolve_plan_returns_deterministic_http_plan(session) -> None:
    source_version_id = await _seed(
        session,
        spec={
            "provider": "deterministic_http",
            "seed_urls": ["https://example.com/a", "https://example.com/b"],
        },
    )

    _, _, plan = await resolve_plan(session, _build_registry(), source_version_id)

    assert plan.provider == "deterministic_http"
    assert plan.seed_urls == ["https://example.com/a", "https://example.com/b"]
    assert plan.estimated_request_count == 2


@pytest.mark.asyncio
async def test_resolve_plan_raises_when_source_version_missing(session) -> None:
    with pytest.raises(NotFoundError):
        await resolve_plan(session, _build_registry(), "sv_missing")


@pytest.mark.asyncio
async def test_format_plan_surfaces_execution_mode_and_seed_urls(session) -> None:
    source_version_id = await _seed(
        session,
        spec={
            "provider": "deterministic_http",
            "seed_urls": ["https://example.com/a"],
        },
        execution_mode=ExecutionMode.SHADOW,
    )

    source, source_version, plan = await resolve_plan(session, _build_registry(), source_version_id)
    rendered = format_plan(source, source_version, plan)

    assert "execution_mode       shadow" in rendered
    assert "provider             deterministic_http" in rendered
    assert "https://example.com/a" in rendered


@pytest.fixture
def _fake_checker_factory():
    from platform_control.services.robots import RobotsChecker

    class _FakeChecker(RobotsChecker):
        def __init__(self, verdicts: dict[str, bool]) -> None:
            super().__init__()
            self._verdicts = verdicts
            self.calls: list[tuple[str, str]] = []

        async def is_allowed(self, url: str, user_agent: str) -> bool:
            self.calls.append((url, user_agent))
            return self._verdicts.get(url, True)

    return _FakeChecker


@pytest.mark.asyncio
async def test_check_seed_robots_returns_verdicts_for_each_seed(
    session, _fake_checker_factory
) -> None:
    from platform_control.cli.plan import check_seed_robots

    source_version_id = await _seed(
        session,
        spec={
            "provider": "deterministic_http",
            "seed_urls": ["https://example.com/a", "https://example.com/b"],
        },
    )
    source, _, plan = await resolve_plan(session, _build_registry(), source_version_id)
    checker = _fake_checker_factory({"https://example.com/a": True, "https://example.com/b": False})

    verdicts = await check_seed_robots(session, source, plan, checker=checker)

    assert {v.url for v in verdicts} == {
        "https://example.com/a",
        "https://example.com/b",
    }
    assert next(v for v in verdicts if v.url.endswith("/a")).allowed is True
    assert next(v for v in verdicts if v.url.endswith("/b")).allowed is False


@pytest.mark.asyncio
async def test_check_seed_robots_uses_policy_user_agent_when_attached(
    session, _fake_checker_factory
) -> None:
    from platform_control.cli.plan import check_seed_robots
    from platform_control.domain import RobotsMode
    from platform_control.models.compliance_policy import CompliancePolicy

    # Attach a policy with a known contact_url -> UA should include it.
    policy = CompliancePolicy(
        name="ua-test",
        robots_mode=RobotsMode.STRICT,
        contact_url="https://evidara.ai/contact",
    )
    session.add(policy)
    await session.flush()
    source_version_id = await _seed(
        session,
        spec={
            "provider": "deterministic_http",
            "seed_urls": ["https://example.com/a"],
        },
    )
    # Attach policy after _seed by updating jurisdiction.
    from platform_control.models.authority import Jurisdiction as _Jur

    jur = await session.get(_Jur, "jur_ch")
    jur.compliance_policy_id = policy.compliance_policy_id
    await session.commit()

    source, _, plan = await resolve_plan(session, _build_registry(), source_version_id)
    checker = _fake_checker_factory({"https://example.com/a": True})

    verdicts = await check_seed_robots(session, source, plan, checker=checker)

    assert len(verdicts) == 1
    assert "https://evidara.ai/contact" in verdicts[0].user_agent


@pytest.mark.asyncio
async def test_format_robots_verdicts_surfaces_disallow() -> None:
    from platform_control.cli.plan import RobotsVerdict, format_robots_verdicts

    rendered = format_robots_verdicts(
        [
            RobotsVerdict(url="https://example.com/a", allowed=True, user_agent="ua"),
            RobotsVerdict(url="https://example.com/b", allowed=False, user_agent="ua"),
        ]
    )
    assert "robots_check:" in rendered
    assert "DISALLOWED" in rendered
    assert "allowed" in rendered
    assert "https://example.com/b" in rendered


@pytest.mark.asyncio
async def test_format_robots_verdicts_empty() -> None:
    from platform_control.cli.plan import format_robots_verdicts

    rendered = format_robots_verdicts([])
    assert "no seed URLs" in rendered
