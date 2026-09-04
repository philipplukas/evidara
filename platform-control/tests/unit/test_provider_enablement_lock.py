"""The ADR-0030 two-key lock, enforced on the run-launch path (#559).

A run may only fire at a live government portal when BOTH keys are turned:

- config owner: the blueprint template carries `enabled: true`
  (`source_blueprints.yaml`), and
- code owner: the resolved provider declares `live_ready = True`
  (`start_run` is not a stub).

These tests are the guarantee the ADR sells: a disabled template cannot launch
a run, a scaffold provider cannot launch a run even if a template referencing it
were mistakenly enabled, and a live + enabled template (the CH Fedlex canary
driven by `scripts/ch-fedlex-fast-loop.sh`) still launches.
"""

from __future__ import annotations

from dataclasses import dataclass, field

import pytest
from conftest import dispatchable_compliance_policy
from sqlalchemy import select

from acquisition_core.providers import (
    AcquisitionReadiness,
    ProviderNotLiveReadyError,
    ensure_launchable,
    provider_readiness,
)
from platform_control.domain import RunMode, RunStatus
from platform_control.errors import (
    BlueprintTemplateNotEnabledError,
    InvalidStateTransitionError,
)
from platform_control.models.authority import Authority, Jurisdiction
from platform_control.models.provider_job import ProviderJob
from platform_control.models.run import Run
from platform_control.schemas.run import CreateRunRequest
from platform_control.schemas.source import (
    BlueprintSeedOverride,
    CreateSourceRequest,
    CreateSourceVersionRequest,
)
from platform_control.services.acquisition_provider import ProviderStartResult
from platform_control.services.blueprint_enablement import BlueprintEnablementService
from platform_control.services.canton_http_provider import CantonHttpProvider
from platform_control.services.provider_registry import ProviderRegistry
from platform_control.services.run_service import RunService
from platform_control.services.source_service import SourceService

# Templates this test pins, and why (see source_blueprints.yaml):
# - ch/fedlex_sparql_constitution_de : live provider + enabled  -> must launch
# - de/bundesland_http_bayern        : live provider + disabled -> config key blocks
# - ch/canton_http_zh                : scaffold provider + disabled -> code key blocks
LIVE_TEMPLATE = ("ch", "fedlex_sparql_constitution_de")
DISABLED_TEMPLATE = ("de", "bundesland_http_bayern")
SCAFFOLD_TEMPLATE = ("ch", "canton_http_zh")


@dataclass
class RecordingProvider:
    """Stands in for a live_ready provider — records calls, no network."""

    provider_name: str = "fedlex_sparql"
    live_ready: bool = True
    calls: list[str] = field(default_factory=list)

    async def start_run(self, source, source_version, run) -> ProviderStartResult:
        del source, source_version
        self.calls.append(run.run_id)
        return ProviderStartResult(
            provider=self.provider_name,
            external_job_id=f"job_{run.run_id}",
            request_payload={},
            response_payload={},
        )


def _registry() -> tuple[ProviderRegistry, dict[str, RecordingProvider]]:
    registry = ProviderRegistry()
    live = {
        "fedlex_sparql": RecordingProvider(provider_name="fedlex_sparql"),
        "bundesland_http": RecordingProvider(provider_name="bundesland_http"),
    }
    for provider in live.values():
        registry.register(provider)
    # The real scaffold: live_ready = False, start_run raises NotImplementedError.
    registry.register(CantonHttpProvider())
    return registry, live


async def _source_version_from_template(session, template: tuple[str, str]):
    overlay_id, provider_template_id = template
    policy = dispatchable_compliance_policy()
    session.add(policy)
    session.add(
        Jurisdiction(
            jurisdiction_id="jur_ch_federal",
            name="Switzerland",
            slug="ch",
            compliance_policy_id=policy.compliance_policy_id,
        )
    )
    session.add(
        Authority(
            authority_id="auth_fedlex",
            jurisdiction_id="jur_ch_federal",
            name="Fedlex",
            slug="fedlex",
        )
    )
    await session.commit()

    source_service = SourceService(session)
    source = await source_service.create_source(
        CreateSourceRequest(
            name="Federal legislation",
            jurisdiction_id="jur_ch_federal",
            authority_id="auth_fedlex",
        )
    )
    version = await source_service.create_source_version(
        source.source_id,
        CreateSourceVersionRequest(
            version_label="v1",
            overlay_id=overlay_id,
            provider_template_id=provider_template_id,
        ),
    )
    return source, version


def _preview_run(source_id: str, source_version_id: str) -> CreateRunRequest:
    return CreateRunRequest(
        source_id=source_id,
        source_version_id=source_version_id,
        mode=RunMode.PREVIEW,
    )


@pytest.mark.asyncio
async def test_source_version_records_blueprint_provenance(session) -> None:
    # The lock re-reads the template's `enabled` flag at dispatch time, which
    # only works because the version remembers which template it came from.
    _, version = await _source_version_from_template(session, LIVE_TEMPLATE)
    assert (version.overlay_id, version.provider_template_id) == LIVE_TEMPLATE


@pytest.mark.asyncio
async def test_disabled_template_cannot_launch_a_run(session) -> None:
    # Config-owner key: bundesland_http IS live_ready, so only the template's
    # `enabled: false` stands between this run and the live Bavarian portal.
    source, version = await _source_version_from_template(session, DISABLED_TEMPLATE)
    registry, live = _registry()
    run_service = RunService(session, provider_registry=registry)

    with pytest.raises(BlueprintTemplateNotEnabledError):
        await run_service.create_run(_preview_run(source.source_id, version.source_version_id))

    assert live["bundesland_http"].calls == []
    # The refusal is recorded as a terminal FAILED run (evidence, #634) — never a
    # PENDING one, so no worker picks it up.
    runs = list(await session.scalars(select(Run)))
    assert len(runs) == 1
    assert runs[0].status is RunStatus.FAILED
    assert "not enabled" in (runs[0].failure_reason or "")
    assert runs[0].run_metadata.get("refused") is True


@pytest.mark.asyncio
async def test_scaffold_provider_cannot_launch_even_if_template_is_enabled(session) -> None:
    # Code-owner key: an operator flips the config key on (the real, DB-backed
    # override path, #632) for a template whose provider is still a scaffold
    # (canton_http, live_ready=False). The provider key must still refuse to fire
    # at the cantonal portal.
    source, version = await _source_version_from_template(session, SCAFFOLD_TEMPLATE)
    await BlueprintEnablementService(session).set_enabled(
        *SCAFFOLD_TEMPLATE, enabled=True, note="operator flipped it", actor="op_local_dev"
    )
    await session.commit()
    registry, _ = _registry()
    run_service = RunService(session, provider_registry=registry)

    with pytest.raises(ProviderNotLiveReadyError):
        await run_service.create_run(_preview_run(source.source_id, version.source_version_id))

    # Code-key refusal is recorded as a terminal FAILED run (evidence, #634).
    runs = list(await session.scalars(select(Run)))
    assert len(runs) == 1
    assert runs[0].status is RunStatus.FAILED
    assert runs[0].run_metadata.get("refused") is True


@pytest.mark.asyncio
async def test_scaffold_provider_cannot_launch_from_a_handwritten_spec(session) -> None:
    # Versions built from a hand-written acquisition_spec carry no template, so
    # the provider key is the only one that applies — and it must hold.
    source, version = await _source_version_from_template(session, SCAFFOLD_TEMPLATE)
    version.overlay_id = None
    version.provider_template_id = None
    await session.commit()

    registry, _ = _registry()
    run_service = RunService(session, provider_registry=registry)

    with pytest.raises(ProviderNotLiveReadyError):
        await run_service.create_run(_preview_run(source.source_id, version.source_version_id))


@pytest.mark.asyncio
async def test_live_ready_provider_with_enabled_template_launches(session) -> None:
    # Both keys turned: the CH Fedlex canary template must keep launching runs.
    source, version = await _source_version_from_template(session, LIVE_TEMPLATE)
    registry, live = _registry()
    run_service = RunService(session, provider_registry=registry)

    run = await run_service.create_run(_preview_run(source.source_id, version.source_version_id))

    assert run.status is RunStatus.RUNNING
    assert live["fedlex_sparql"].calls == [run.run_id]
    jobs = list(await session.scalars(select(ProviderJob).where(ProviderJob.run_id == run.run_id)))
    assert len(jobs) == 1


@pytest.mark.asyncio
async def test_worker_dispatch_fails_locked_runs_instead_of_retrying_them(session) -> None:
    # A PENDING run whose template was disabled after the run was queued must be
    # failed, not retried on every poll cycle (poison pill in connector_worker).
    source, version = await _source_version_from_template(session, LIVE_TEMPLATE)
    registry, live = _registry()
    run_service = RunService(session, provider_registry=registry)

    run = Run(
        source_id=source.source_id,
        source_version_id=version.source_version_id,
        mode=RunMode.PREVIEW,
        status=RunStatus.PENDING,
    )
    session.add(run)
    await session.commit()

    version.overlay_id, version.provider_template_id = DISABLED_TEMPLATE
    await session.commit()

    dispatched = await run_service.dispatch_pending_runs()

    assert dispatched == 0
    assert live["fedlex_sparql"].calls == []
    await session.refresh(run)
    assert run.status is RunStatus.FAILED
    assert "not enabled" in (run.failure_reason or "")


@pytest.mark.asyncio
async def test_a_refusal_is_auditable_through_the_run_collection(session) -> None:
    """A refusal recorded but not readable back is not evidence (#634, item 4).

    #637 began writing a terminal FAILED run when the lock refuses a dispatch,
    but the `refused` marker lived only in `metadata` and no response schema
    exposed it — so "what did we try to onboard and why did it refuse?" was
    still unanswerable over the API. This pins the readback and the filter.
    """
    source, version = await _source_version_from_template(session, DISABLED_TEMPLATE)
    registry, _ = _registry()
    run_service = RunService(session, provider_registry=registry)

    with pytest.raises(BlueprintTemplateNotEnabledError):
        await run_service.create_run(_preview_run(source.source_id, version.source_version_id))

    # A genuine (non-refused) run alongside it, so the filter has to discriminate
    # rather than trivially returning everything.
    session.add(
        Run(
            source_id=source.source_id,
            source_version_id=version.source_version_id,
            mode=RunMode.PREVIEW,
            status=RunStatus.FAILED,
            failure_reason="upstream 503",
        )
    )
    await session.commit()

    everything, total = await run_service.list_runs()
    assert total == 2
    assert sorted(item.refused for item in everything) == [False, True]

    refusals, refused_total = await run_service.list_runs(refused=True)
    assert refused_total == 1
    assert refusals[0].refused is True
    assert "not enabled" in (refusals[0].failure_reason or "")

    # `refused=False` must also match rows with no marker at all — every run
    # that predates the refusal record, plus the ordinary failure above.
    genuine, genuine_total = await run_service.list_runs(refused=False)
    assert genuine_total == 1
    assert genuine[0].refused is False
    assert genuine[0].failure_reason == "upstream 503"


# ─── provider_readiness fail-closed (#743 review round 2) ───────────────────
#
# The docstring promises "unknown must never mean launchable", and a mutation
# pass proved both halves of that promise could be inverted to fail-OPEN with
# 589 tests green: `provider_readiness` is only ever exercised against real
# providers that all declare a valid `readiness`, so the legacy-bool path and
# both SCAFFOLD defaults had no coverage at all. An unrecognised state opening
# the lock means dispatching at a live portal on a provider nobody vouched for.


class _NoReadinessDeclared:
    provider_name = "no_readiness"


class _BogusReadiness:
    provider_name = "bogus"
    readiness = "definitely_not_a_state"


class _NoneReadiness:
    provider_name = "none_readiness"
    readiness = None


class _TruthyNonEnum:
    provider_name = "truthy"
    readiness = 1


class _LegacyBoolTrue:
    provider_name = "legacy_true"
    live_ready = True


class _LegacyBoolFalse:
    provider_name = "legacy_false"
    live_ready = False


@pytest.mark.parametrize(
    "provider",
    [_NoReadinessDeclared, _BogusReadiness, _NoneReadiness, _TruthyNonEnum, _LegacyBoolFalse],
)
def test_unknown_or_missing_readiness_fails_closed(provider) -> None:
    assert provider_readiness(provider) is AcquisitionReadiness.SCAFFOLD
    # And fails closed at the lock too, in BOTH modes — an unrecognised state
    # must not be admitted by the acceptance exemption either.
    with pytest.raises(ProviderNotLiveReadyError):
        ensure_launchable(provider)
    with pytest.raises(ProviderNotLiveReadyError):
        ensure_launchable(provider, for_acceptance=True)


def test_legacy_live_ready_bool_still_maps_to_live() -> None:
    # Third-party and test doubles predating the enum keep working; this is the
    # shim that let 576 of 580 existing tests pass untouched.
    assert provider_readiness(_LegacyBoolTrue) is AcquisitionReadiness.LIVE
    ensure_launchable(_LegacyBoolTrue)


def test_readiness_wins_over_a_contradicting_legacy_bool() -> None:
    # The enum is authoritative. A runbook telling an engineer to set
    # `live_ready = False` as a rollback would be a silent no-op, which is why
    # ch-bger-live-enablement.md now warns about exactly this.
    class _Contradictory:
        provider_name = "contradictory"
        readiness = AcquisitionReadiness.AWAITING_EVIDENCE
        live_ready = True

    assert provider_readiness(_Contradictory) is AcquisitionReadiness.AWAITING_EVIDENCE
    with pytest.raises(ProviderNotLiveReadyError):
        ensure_launchable(_Contradictory)


@pytest.mark.asyncio
async def test_seed_override_cannot_bypass_the_config_key(session) -> None:
    """#710/ADR-0046: the "template plus my seeds" rung is inside the lock.

    The obvious way to break the lock with an override path is to use it as a
    laundering device: name a disabled template, supply your own seeds, and hope
    the resulting version reads as hand-written (provenance NULL) — because a
    version with no provenance is never measured against any config key at all
    (`run_service._assert_launchable` only consults the enablement service when
    both provenance fields are set).

    So the override must *keep* provenance, not drop it. bundesland_http is
    live_ready, so `enabled: false` on the Bavarian template is the only thing
    between this run and the live portal — with or without operator seeds.
    """
    overlay_id, provider_template_id = DISABLED_TEMPLATE
    policy = dispatchable_compliance_policy()
    session.add(policy)
    session.add(
        Jurisdiction(
            jurisdiction_id="jur_de_by",
            name="Bayern",
            slug="de-by",
            compliance_policy_id=policy.compliance_policy_id,
        )
    )
    session.add(
        Authority(
            authority_id="auth_de_by",
            jurisdiction_id="jur_de_by",
            name="Bayern",
            slug="de-by",
        )
    )
    await session.commit()

    source_service = SourceService(session)
    source = await source_service.create_source(
        CreateSourceRequest(
            name="Bayern Landesrecht",
            jurisdiction_id="jur_de_by",
            authority_id="auth_de_by",
        )
    )
    version = await source_service.create_source_version(
        source.source_id,
        CreateSourceVersionRequest(
            version_label="v1",
            overlay_id=overlay_id,
            provider_template_id=provider_template_id,
            blueprint_overrides=BlueprintSeedOverride(
                seed_url="https://www.gesetze-bayern.de/Content/Document/BayTierSchG"
            ),
        ),
    )

    # Provenance is intact, so the config key still applies to this version.
    assert (version.overlay_id, version.provider_template_id) == DISABLED_TEMPLATE

    registry, live = _registry()
    run_service = RunService(session, provider_registry=registry)
    with pytest.raises(BlueprintTemplateNotEnabledError):
        await run_service.create_run(_preview_run(source.source_id, version.source_version_id))

    assert live["bundesland_http"].calls == []


@pytest.mark.asyncio
async def test_seed_override_cannot_redirect_an_enabled_template_at_a_new_portal(
    session,
) -> None:
    """The other half: an *enabled* template's key is evidence about one portal.

    ch/fedlex_sparql_constitution_de is enabled and live_ready — the one template
    combination in this file that does launch. If an operator could hand it an
    arbitrary seed origin, every enabled template would be a general-purpose
    licence to crawl, and the acceptance-run evidence behind that key would mean
    nothing. The refusal happens before any version exists.
    """
    source, _ = await _source_version_from_template(session, LIVE_TEMPLATE)
    source_service = SourceService(session)

    with pytest.raises(InvalidStateTransitionError, match="outside this blueprint template"):
        await source_service.create_source_version(
            source.source_id,
            CreateSourceVersionRequest(
                version_label="v2",
                overlay_id=LIVE_TEMPLATE[0],
                provider_template_id=LIVE_TEMPLATE[1],
                blueprint_overrides=BlueprintSeedOverride(
                    seed_url="https://evil.example/eli/cc/1999/404"
                ),
            ),
        )
