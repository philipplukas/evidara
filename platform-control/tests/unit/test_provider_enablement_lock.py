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
from sqlalchemy import select

from acquisition_core.providers import ProviderNotLiveReadyError
from platform_control.domain import RunMode, RunStatus
from platform_control.errors import BlueprintTemplateNotEnabledError
from platform_control.models.authority import Authority, Jurisdiction
from platform_control.models.provider_job import ProviderJob
from platform_control.models.run import Run
from platform_control.schemas.run import CreateRunRequest
from platform_control.schemas.source import CreateSourceRequest, CreateSourceVersionRequest
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
    session.add(Jurisdiction(jurisdiction_id="jur_ch_federal", name="Switzerland", slug="ch"))
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
