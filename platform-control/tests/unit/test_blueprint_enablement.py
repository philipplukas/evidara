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
from platform_control.schemas.source import CreateSourceRequest, CreateSourceVersionRequest
from platform_control.services.blueprint_enablement import BlueprintEnablementService
from platform_control.services.provider_registry_factory import build_provider_registry
from platform_control.services.run_service import RunService
from platform_control.services.source_service import SourceService

# See source_blueprints.yaml: canton_http_zh is a scaffold provider (live_ready
# False) shipped disabled; fedlex_sparql_constitution_de is live + enabled.
SCAFFOLD_TEMPLATE = ("ch", "canton_http_zh")
LIVE_TEMPLATE = ("ch", "fedlex_sparql_constitution_de")


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
    assert "live-ready" in lock.detail.lower()


def _settings():
    from platform_control.config import get_settings

    return get_settings()
