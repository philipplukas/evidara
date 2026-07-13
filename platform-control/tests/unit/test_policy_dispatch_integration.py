"""End-to-end check: CompliancePolicy attached to a Jurisdiction actually
shapes the provider's runtime through the politeness ContextVar.

The individual pieces (RateLimiterRegistry, current_rate_limiter, limited_get)
have unit tests; this test stitches them through RunService so a regression in
the wiring — e.g. forgetting the set/reset pair, or resolving via the wrong
helper — fails loudly.
"""

from __future__ import annotations

from dataclasses import dataclass

import pytest

from platform_control.domain import RobotsMode, SourceVersionStatus
from platform_control.models.authority import Authority, Jurisdiction
from platform_control.models.compliance_policy import CompliancePolicy
from platform_control.models.source import Source
from platform_control.models.source_version import SourceVersion
from platform_control.schemas.run import CreateRunRequest
from platform_control.services.acquisition_provider import ProviderStartResult
from platform_control.services.politeness import HostRateLimiter, current_rate_limiter
from platform_control.services.provider_registry import ProviderRegistry
from platform_control.services.run_service import RunService


@dataclass
class _LimiterObservingProvider:
    """Provider stub that snapshots ``current_rate_limiter`` during start_run."""

    provider_name: str = "deterministic_http"
    live_ready: bool = True
    observed: HostRateLimiter | None = None
    observed_once: bool = False

    async def start_run(self, source, source_version, run) -> ProviderStartResult:
        del source, source_version
        self.observed = current_rate_limiter.get()
        self.observed_once = True
        return ProviderStartResult(
            provider=self.provider_name,
            external_job_id=f"obs_{run.run_id}",
            request_payload={},
            response_payload={"captured": 0},
        )


async def _seed_jurisdiction_with_policy(
    session,
    *,
    requests_per_minute: int,
    max_concurrent: int,
) -> str:
    policy = CompliancePolicy(
        name="ch-politeness",
        robots_mode=RobotsMode.STRICT,
        max_requests_per_minute_per_host=requests_per_minute,
        max_concurrent_per_host=max_concurrent,
    )
    session.add(policy)
    await session.flush()

    session.add(
        Jurisdiction(
            jurisdiction_id="jur_ch",
            name="Switzerland",
            slug="ch",
            compliance_policy_id=policy.compliance_policy_id,
        )
    )
    session.add(
        Authority(
            authority_id="auth_zh_admin",
            jurisdiction_id="jur_ch",
            name="Zurich Administrative Court",
            slug="zh-admin-court",
        )
    )
    source = Source(
        source_id="src_obs",
        name="Zurich decisions",
        jurisdiction_id="jur_ch",
        authority_id="auth_zh_admin",
    )
    session.add(source)
    await session.flush()
    session.add(
        SourceVersion(
            source_version_id="sv_obs",
            source_id="src_obs",
            version_label="v1",
            status=SourceVersionStatus.APPROVED,
            acquisition_spec={
                "provider": "deterministic_http",
                "seed_urls": ["https://example.com/"],
            },
        )
    )
    await session.commit()
    return "src_obs"


@pytest.mark.asyncio
async def test_policy_attached_to_jurisdiction_reaches_provider_via_contextvar(
    session,
) -> None:
    await _seed_jurisdiction_with_policy(session, requests_per_minute=45, max_concurrent=3)
    provider = _LimiterObservingProvider()
    registry = ProviderRegistry()
    registry.register(provider)
    service = RunService(session=session, provider_registry=registry)

    await service.create_run(CreateRunRequest(source_id="src_obs", source_version_id="sv_obs"))

    assert provider.observed_once is True
    assert provider.observed is not None
    assert provider.observed.max_requests_per_minute == 45
    assert provider.observed.max_concurrent == 3


@pytest.mark.asyncio
async def test_contextvar_is_reset_after_dispatch(session) -> None:
    await _seed_jurisdiction_with_policy(session, requests_per_minute=60, max_concurrent=2)
    provider = _LimiterObservingProvider()
    registry = ProviderRegistry()
    registry.register(provider)
    service = RunService(session=session, provider_registry=registry)

    assert current_rate_limiter.get() is None
    await service.create_run(CreateRunRequest(source_id="src_obs", source_version_id="sv_obs"))
    assert current_rate_limiter.get() is None


@pytest.mark.asyncio
async def test_jurisdiction_without_policy_keeps_contextvar_unset(session) -> None:
    session.add(Jurisdiction(jurisdiction_id="jur_ch", name="Switzerland", slug="ch"))
    session.add(
        Authority(
            authority_id="auth_zh_admin",
            jurisdiction_id="jur_ch",
            name="Zurich Administrative Court",
            slug="zh-admin-court",
        )
    )
    source = Source(
        source_id="src_nopolicy",
        name="Zurich decisions",
        jurisdiction_id="jur_ch",
        authority_id="auth_zh_admin",
    )
    session.add(source)
    await session.flush()
    session.add(
        SourceVersion(
            source_version_id="sv_nopolicy",
            source_id="src_nopolicy",
            version_label="v1",
            status=SourceVersionStatus.APPROVED,
            acquisition_spec={
                "provider": "deterministic_http",
                "seed_urls": ["https://example.com/"],
            },
        )
    )
    await session.commit()

    provider = _LimiterObservingProvider()
    registry = ProviderRegistry()
    registry.register(provider)
    service = RunService(session=session, provider_registry=registry)

    await service.create_run(
        CreateRunRequest(source_id="src_nopolicy", source_version_id="sv_nopolicy")
    )

    assert provider.observed_once is True
    assert provider.observed is None
