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

    source, source_version, plan = await resolve_plan(
        session, _build_registry(), source_version_id
    )
    rendered = format_plan(source, source_version, plan)

    assert "execution_mode       shadow" in rendered
    assert "provider             deterministic_http" in rendered
    assert "https://example.com/a" in rendered
