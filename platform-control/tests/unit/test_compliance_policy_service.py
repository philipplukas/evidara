from __future__ import annotations

import pytest

from platform_control.domain import RobotsMode
from platform_control.models.authority import Authority, Jurisdiction
from platform_control.models.compliance_policy import CompliancePolicy
from platform_control.models.source import Source
from platform_control.services.compliance_policy_service import (
    RateLimiterRegistry,
    resolve_rate_limiter_for_source,
)
from platform_control.services.politeness import HostRateLimiter


async def _seed_source(session, *, with_policy: bool) -> Source:
    if with_policy:
        policy = CompliancePolicy(
            name="ch-default",
            robots_mode=RobotsMode.STRICT,
            max_requests_per_minute_per_host=30,
            max_concurrent_per_host=1,
        )
        session.add(policy)
        await session.flush()
        jurisdiction = Jurisdiction(
            jurisdiction_id="jur_ch",
            name="Switzerland",
            slug="ch",
            compliance_policy_id=policy.compliance_policy_id,
        )
    else:
        jurisdiction = Jurisdiction(
            jurisdiction_id="jur_ch",
            name="Switzerland",
            slug="ch",
        )
    session.add(jurisdiction)
    session.add(
        Authority(
            authority_id="auth_zh_admin",
            jurisdiction_id="jur_ch",
            name="Zurich Administrative Court",
            slug="zh-admin-court",
        )
    )
    source = Source(
        source_id="src_seed",
        name="Zurich decisions",
        jurisdiction_id="jur_ch",
        authority_id="auth_zh_admin",
    )
    session.add(source)
    await session.commit()
    return source


@pytest.mark.asyncio
async def test_resolve_returns_none_when_no_policy_attached(session) -> None:
    source = await _seed_source(session, with_policy=False)
    registry = RateLimiterRegistry()

    limiter = await resolve_rate_limiter_for_source(session, source, registry)

    assert limiter is None


@pytest.mark.asyncio
async def test_resolve_returns_limiter_shaped_by_policy(session) -> None:
    source = await _seed_source(session, with_policy=True)
    registry = RateLimiterRegistry()

    limiter = await resolve_rate_limiter_for_source(session, source, registry)

    assert limiter is not None
    assert isinstance(limiter, HostRateLimiter)
    assert limiter.max_requests_per_minute == 30
    assert limiter.max_concurrent == 1


@pytest.mark.asyncio
async def test_registry_caches_limiter_so_buckets_persist_across_runs(session) -> None:
    source = await _seed_source(session, with_policy=True)
    registry = RateLimiterRegistry()

    first = await resolve_rate_limiter_for_source(session, source, registry)
    second = await resolve_rate_limiter_for_source(session, source, registry)

    assert first is second
