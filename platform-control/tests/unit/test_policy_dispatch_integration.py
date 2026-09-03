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
from sqlalchemy import select

from platform_control.domain import ExecutionMode, RobotsMode, RunStatus, SourceVersionStatus
from platform_control.errors import CompliancePolicyMissingError
from platform_control.models.authority import Authority, Jurisdiction
from platform_control.models.compliance_policy import CompliancePolicy
from platform_control.models.run import Run
from platform_control.models.source import Source
from platform_control.models.source_version import SourceVersion
from platform_control.schemas.run import CreateRunRequest
from platform_control.services.acquisition_provider import ProviderStartResult
from platform_control.services.compliance_policy_service import COMPLIANCE_POLICY_MISSING
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


async def _seed_jurisdiction_without_policy(
    session, *, execution_mode: ExecutionMode = ExecutionMode.LIVE
) -> None:
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
            execution_mode=execution_mode,
            acquisition_spec={
                "provider": "deterministic_http",
                "seed_urls": ["https://example.com/"],
            },
        )
    )
    await session.commit()


@pytest.mark.asyncio
async def test_jurisdiction_without_policy_refuses_the_dispatch(session) -> None:
    """A missing policy REFUSES; it does not mean "no limits".

    This test previously asserted the opposite — that the contextvar stayed
    unset and the provider ran anyway. That was the whole defect: the seed tree
    declares `compliance_policy_id` on Fedlex and AT-RIS and nowhere else, so
    every cantonal source resolved to `None` and `limited_get` fell through to a
    bare `client.get`, unpaced and robots-blind. The permissive reading was
    pinned by a green test, which is why it survived.

    Inheriting `jur_ch`'s policy instead is the other wrong answer, and the more
    dangerous one: `jur_ch` carries `cp_ch_fedlex_open_data`
    (`robots_mode: ignore`, 600 rpm), which no canton is entitled to.
    """
    await _seed_jurisdiction_without_policy(session)

    provider = _LimiterObservingProvider()
    registry = ProviderRegistry()
    registry.register(provider)
    service = RunService(session=session, provider_registry=registry)

    with pytest.raises(CompliancePolicyMissingError) as excinfo:
        await service.create_run(
            CreateRunRequest(source_id="src_nopolicy", source_version_id="sv_nopolicy")
        )

    # The named code, not just prose — an operator auditing `?refused=true`
    # groups by cause without parsing English.
    assert str(excinfo.value).startswith(f"{COMPLIANCE_POLICY_MISSING}:")
    # And the provider was never reached: the refusal happens before dispatch,
    # so no request left the process.
    assert provider.observed_once is False


@pytest.mark.asyncio
async def test_the_refusal_is_recorded_as_an_auditable_failed_run(session) -> None:
    """A refusal that leaves no trace is a hole (#634) — same contract as the two-key lock."""
    await _seed_jurisdiction_without_policy(session)

    provider = _LimiterObservingProvider()
    registry = ProviderRegistry()
    registry.register(provider)
    service = RunService(session=session, provider_registry=registry)

    with pytest.raises(CompliancePolicyMissingError):
        await service.create_run(
            CreateRunRequest(source_id="src_nopolicy", source_version_id="sv_nopolicy")
        )

    runs = list(await session.scalars(select(Run)))
    assert len(runs) == 1
    assert runs[0].status is RunStatus.FAILED
    assert runs[0].run_metadata["refused"] is True
    assert COMPLIANCE_POLICY_MISSING in runs[0].failure_reason


@pytest.mark.asyncio
async def test_shadow_versions_are_exempt_from_the_policy_requirement(session) -> None:
    """SHADOW replays cassettes, so no request reaches the host a policy protects.

    Same exemption `_require_launchable` grants, for the same reason. Requiring
    a politeness policy for a run that cannot be impolite would be theatre, and
    would block the one rehearsal mode that is safe by construction.
    """
    await _seed_jurisdiction_without_policy(session, execution_mode=ExecutionMode.SHADOW)

    # SHADOW resolves to the cassette provider, so that is the one to observe.
    provider = _LimiterObservingProvider(provider_name="cassette")
    registry = ProviderRegistry()
    registry.register(provider)
    service = RunService(session=session, provider_registry=registry)

    await service.create_run(
        CreateRunRequest(source_id="src_nopolicy", source_version_id="sv_nopolicy")
    )

    assert provider.observed_once is True
    assert provider.observed is None


@pytest.mark.asyncio
async def test_a_cantonal_jurisdiction_does_not_inherit_its_parents_policy(session) -> None:
    """The inheritance decision, pinned.

    `jur_ch_zh`'s parent `jur_ch` HAS a policy here. If `_resolve_policy_for_source`
    ever grows a parent fallback, this test goes green in the wrong direction —
    the canton would silently acquire an open-data posture written for the
    Federal Chancellery's programme, which it is not part of.
    """
    parent_policy = CompliancePolicy(
        name="parent-open-data",
        robots_mode=RobotsMode.IGNORE,
        max_requests_per_minute_per_host=600,
    )
    session.add(parent_policy)
    await session.flush()
    session.add(
        Jurisdiction(
            jurisdiction_id="jur_ch",
            name="Switzerland",
            slug="ch",
            compliance_policy_id=parent_policy.compliance_policy_id,
        )
    )
    session.add(
        Jurisdiction(
            jurisdiction_id="jur_ch_zh",
            name="Kanton Zürich",
            slug="ch-zh",
            parent_id="jur_ch",
        )
    )
    session.add(
        Authority(
            authority_id="auth_zh_sk",
            jurisdiction_id="jur_ch_zh",
            name="Staatskanzlei Kanton Zürich",
            slug="zh-staatskanzlei",
        )
    )
    source = Source(
        source_id="src_zh",
        name="ZH systematic collection",
        jurisdiction_id="jur_ch_zh",
        authority_id="auth_zh_sk",
    )
    session.add(source)
    await session.flush()
    session.add(
        SourceVersion(
            source_version_id="sv_zh",
            source_id="src_zh",
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

    with pytest.raises(CompliancePolicyMissingError):
        await service.create_run(CreateRunRequest(source_id="src_zh", source_version_id="sv_zh"))
