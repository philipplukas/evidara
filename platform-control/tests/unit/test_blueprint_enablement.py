"""The operator-reachable config key (#632) and its surfacing (#634).

ADR-0030's config-owner key used to be YAML inside the package — an engineer and
a deploy to flip. These tests pin the DB-backed override that makes it an
operator action: the effective key is `override ?? shipped default`, flipping it
records an audit trail, and the run-launch pre-flight/readiness now evaluate it
so the panel and the operator see an inert template as inert.
"""

from __future__ import annotations

import pytest

from platform_control.domain import RunMode
from platform_control.errors import NotFoundError
from platform_control.models.authority import Authority, Jurisdiction
from platform_control.schemas.source import (
    CreateSourceRequest,
    CreateSourceVersionRequest,
    SourceBlueprintPreviewRequest,
)
from platform_control.services.blueprint_enablement import BlueprintEnablementService
from platform_control.services.provider_registry_factory import build_provider_registry
from platform_control.services.run_service import RunService
from platform_control.services.source_service import SourceService

# See source_blueprints.yaml: canton_http_zh is a real scaffold (start_run is not
# implemented) shipped disabled; fedlex_sparql_constitution_de is live + enabled;
# the gemeinde template's provider is implemented but has no acceptance evidence.
SCAFFOLD_TEMPLATE = ("ch", "canton_http_zh")
LIVE_TEMPLATE = ("ch", "fedlex_sparql_constitution_de")
AWAITING_EVIDENCE_TEMPLATE = ("ch", "gemeinde_http_zh_stadt_hundevorschriften")


async def _seed_reference(session) -> None:
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


@pytest.mark.asyncio
async def test_shipped_default_is_used_when_no_override(session) -> None:
    service = BlueprintEnablementService(session)
    assert await service.is_enabled(*SCAFFOLD_TEMPLATE) is False
    assert await service.is_enabled(*LIVE_TEMPLATE) is True

    state = await service.get_state(*SCAFFOLD_TEMPLATE)
    assert state.source == "default"
    assert state.enabled is False
    assert state.default_enabled is False


@pytest.mark.asyncio
async def test_override_wins_over_shipped_default(session) -> None:
    service = BlueprintEnablementService(session)
    state = await service.set_enabled(
        *SCAFFOLD_TEMPLATE, enabled=True, note="evidence captured", actor="op_local_dev"
    )
    await session.commit()

    assert state.source == "override"
    assert state.enabled is True
    assert state.default_enabled is False  # the shipped default is still False
    assert state.updated_by == "op_local_dev"
    assert state.note == "evidence captured"
    assert await service.is_enabled(*SCAFFOLD_TEMPLATE) is True


@pytest.mark.asyncio
async def test_flip_is_idempotent_upsert_not_duplicate(session) -> None:
    service = BlueprintEnablementService(session)
    await service.set_enabled(*SCAFFOLD_TEMPLATE, enabled=True, note="on", actor="op_a")
    state = await service.set_enabled(*SCAFFOLD_TEMPLATE, enabled=False, note="off", actor="op_b")
    await session.commit()

    assert state.enabled is False
    assert state.updated_by == "op_b"
    assert await service.is_enabled(*SCAFFOLD_TEMPLATE) is False


@pytest.mark.asyncio
async def test_cannot_enable_unknown_template(session) -> None:
    service = BlueprintEnablementService(session)
    with pytest.raises(NotFoundError):
        await service.set_enabled("ch", "does_not_exist", enabled=True, note=None, actor=None)


@pytest.mark.asyncio
async def test_templates_listing_surfaces_the_lock(session) -> None:
    rows = await SourceService(session).list_source_blueprint_templates()
    by_id = {r["provider_template_id"]: r for r in rows}

    scaffold = by_id["canton_http_zh"]
    assert scaffold["enabled"] is False
    assert scaffold["live_ready"] is False
    assert scaffold["launchable"] is False
    assert scaffold["notes"]  # explains why it is inert

    live = by_id["fedlex_sparql_constitution_de"]
    assert live["enabled"] is True
    assert live["live_ready"] is True
    assert live["launchable"] is True
    assert live["notes"] == []


async def _approved_version_from_template(session, template):
    await _seed_reference(session)
    source_service = SourceService(session)
    source = await source_service.create_source(
        CreateSourceRequest(
            name="ZH cantonal law",
            jurisdiction_id="jur_ch_federal",
            authority_id="auth_fedlex",
        )
    )
    version = await source_service.create_source_version(
        source.source_id,
        CreateSourceVersionRequest(
            version_label="v1", overlay_id=template[0], provider_template_id=template[1]
        ),
    )
    return source, version


@pytest.mark.asyncio
async def test_readiness_reports_the_lock_instead_of_lying(session) -> None:
    # Before #634 readiness returned ready:true for an inert template, then the
    # run 400'd. Now the pre-flight itself carries the lock verdict.
    source, version = await _approved_version_from_template(session, SCAFFOLD_TEMPLATE)
    run_service = RunService(session, provider_registry=build_provider_registry(_settings()))

    readiness = await run_service.get_run_readiness(
        source_id=source.source_id,
        source_version_id=version.source_version_id,
        mode=RunMode.PRODUCTION,
    )
    lock = next(c for c in readiness.checks if c.code == "acquisition_lock_open")
    assert lock.ok is False
    assert readiness.ready is False
    assert "not enabled" in lock.detail.lower()


@pytest.mark.asyncio
async def test_readiness_code_key_still_holds_after_config_key_flipped(session) -> None:
    # An operator flips the config key on a scaffold provider: the config half
    # opens, but readiness must still report the code key (live_ready) closed.
    source, version = await _approved_version_from_template(session, SCAFFOLD_TEMPLATE)
    await BlueprintEnablementService(session).set_enabled(
        *SCAFFOLD_TEMPLATE, enabled=True, note="flip", actor="op_local_dev"
    )
    await session.commit()

    run_service = RunService(session, provider_registry=build_provider_registry(_settings()))
    readiness = await run_service.get_run_readiness(
        source_id=source.source_id,
        source_version_id=version.source_version_id,
        mode=RunMode.PRODUCTION,
    )
    lock = next(c for c in readiness.checks if c.code == "acquisition_lock_open")
    assert lock.ok is False
    # The detail must name the remedy, not just the refusal: canton_http is a real
    # scaffold, so this one genuinely does need engineering (#743).
    assert "scaffold" in lock.detail.lower()
    assert "needs engineering" in lock.detail.lower()


@pytest.mark.asyncio
async def test_acceptance_run_is_admitted_for_a_provider_awaiting_evidence(session) -> None:
    """The deadlock break (#743/#735).

    Both ADR-0030 keys are shut for this template, and under the old binary lock
    that was terminal: acceptance evidence required a live run, the live run
    required the code key, and the code key required the evidence. A provider
    could never earn its own first key without an engineer shipping a code change
    — which made every new source an engineering project, the exact failure #628
    measures against.
    """
    source, version = await _approved_version_from_template(session, AWAITING_EVIDENCE_TEMPLATE)
    # Open the config key so the code key is what the production run refuses on.
    # The lock reports the config key first and returns early, so leaving it shut
    # would hide the message under test.
    await BlueprintEnablementService(session).set_enabled(
        *AWAITING_EVIDENCE_TEMPLATE, enabled=True, note="flip", actor="op_local_dev"
    )
    await session.commit()
    run_service = RunService(session, provider_registry=build_provider_registry(_settings()))

    production = await run_service.get_run_readiness(
        source_id=source.source_id,
        source_version_id=version.source_version_id,
        mode=RunMode.PRODUCTION,
    )
    production_lock = next(c for c in production.checks if c.code == "acquisition_lock_open")
    assert production_lock.ok is False
    # Crucially NOT "this needs engineering" — the remedy is a run the operator
    # can dispatch themselves.
    assert "acceptance" in production_lock.detail.lower()
    assert "does not need an engineer" in production_lock.detail.lower()

    acceptance = await run_service.get_run_readiness(
        source_id=source.source_id,
        source_version_id=version.source_version_id,
        mode=RunMode.ACCEPTANCE,
    )
    acceptance_lock = next(c for c in acceptance.checks if c.code == "acquisition_lock_open")
    assert acceptance_lock.ok is True
    # A pass here must not read as "the keys are turned" — it is a rehearsal that
    # produces the evidence for turning them.
    assert "not a production run" in acceptance_lock.detail.lower()


@pytest.mark.asyncio
async def test_acceptance_run_is_still_refused_for_a_real_scaffold(session) -> None:
    # The narrow exemption stays narrow: there is no implementation for an
    # acceptance run to gather evidence about, so ACCEPTANCE must not become a
    # general way past the code key.
    source, version = await _approved_version_from_template(session, SCAFFOLD_TEMPLATE)
    run_service = RunService(session, provider_registry=build_provider_registry(_settings()))

    readiness = await run_service.get_run_readiness(
        source_id=source.source_id,
        source_version_id=version.source_version_id,
        mode=RunMode.ACCEPTANCE,
    )
    lock = next(c for c in readiness.checks if c.code == "acquisition_lock_open")
    assert lock.ok is False
    assert "scaffold" in lock.detail.lower()


def _settings():
    from platform_control.config import get_settings

    return get_settings()


@pytest.mark.asyncio
async def test_blueprint_preview_surfaces_the_providers_own_plan_notes(session) -> None:
    """The system knew the answer and did not say it (#634, item 3).

    Every provider's `plan()` already computes the caveats an operator needs
    before investing in a source, but the only caller in the repo was the `plan`
    CLI — so `blueprint-preview` returned a spec that looked correct while the
    provider had already written down why it was not. These notes are distinct
    from the lock `notes`: the lock explains which key is shut, `plan_notes`
    describe the acquisition itself.
    """
    service = SourceService(session)
    spec = await service.preview_source_blueprint(
        SourceBlueprintPreviewRequest(
            overlay_id="ch", provider_template_id="gemeinde_http_zh_stadt_hundevorschriften"
        )
    )

    plan_notes = service.describe_blueprint_plan_notes(spec)

    # The gemeinde provider resolves the commune and names the open defect that
    # keeps its code key shut — the exact warning #634 found stranded.
    assert any("bfs_number=261" in note for note in plan_notes)
    assert any("readiness=awaiting_evidence" in note for note in plan_notes)


@pytest.mark.asyncio
async def test_plan_notes_degrade_to_empty_rather_than_failing_the_preview(session) -> None:
    # A preview is a read-only pre-flight. If a provider's plan() raises, the
    # operator must still get the lock verdict, not a 500.
    service = SourceService(session)
    spec = await service.preview_source_blueprint(
        SourceBlueprintPreviewRequest(
            overlay_id=LIVE_TEMPLATE[0], provider_template_id=LIVE_TEMPLATE[1]
        )
    )
    spec.provider = "no_such_provider"

    assert service.describe_blueprint_plan_notes(spec) == []
