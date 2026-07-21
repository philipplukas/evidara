"""The operator-reachable config key (#632) and its surfacing (#634).

ADR-0030's config-owner key used to be YAML inside the package — an engineer and
a deploy to flip. These tests pin the DB-backed override that makes it an
operator action: the effective key is `override ?? shipped default`, flipping it
records an audit trail, and the run-launch pre-flight/readiness now evaluate it
so the panel and the operator see an inert template as inert.
"""

from __future__ import annotations

import pytest

from acquisition_core.providers import AcquisitionReadiness, ProviderNotLiveReadyError
from platform_control.domain import RunMode, RunStatus, SourceVersionStatus
from platform_control.errors import BlueprintTemplateNotEnabledError, NotFoundError
from platform_control.models.authority import Authority, Jurisdiction
from platform_control.schemas.run import CreateRunRequest
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
# Was `gemeinde_http_zh_stadt_hundevorschriften` until its acceptance run passed
# (#735, evidence committed 2026-07-20) and moved that provider to `live`. The
# exemplar has to be a provider that is *actually* in the state under test —
# pinning these to one whose readiness has moved on would leave the
# awaiting-evidence branch untested while still appearing covered.
AWAITING_EVIDENCE_TEMPLATE = ("ch", "ch_court_decisions_bger")
# A LIVE provider whose template still ships shut — the #768 case. `gemeinde_http`
# is `readiness = LIVE` (gemeinde_http_provider.py:287) while
# `gemeinde_http_zh_stadt_hundevorschriften` ships `enabled: false`, so the config
# key here has never been turned by anyone. Distinct from LIVE_TEMPLATE, which
# ships enabled.
LIVE_BUT_SHUT_TEMPLATE = ("ch", "gemeinde_http_zh_stadt_hundevorschriften")


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


@pytest.mark.asyncio
async def test_the_listing_gives_each_code_key_state_its_own_remedy(session) -> None:
    """The note bodies are the #743 fix; assert they cannot be swapped.

    A mutation pass swapped the SCAFFOLD and AWAITING_EVIDENCE note strings — so
    a scaffold told the operator "implemented and verified, dispatch an
    acceptance run" and a finished provider was sent to an engineer — and
    nothing failed. That is the original defect reintroduced on the server side,
    which is the half the admin cannot compensate for.
    """
    rows = await SourceService(session).list_source_blueprint_templates()
    by_id = {r["provider_template_id"]: r for r in rows}

    scaffold_notes = " ".join(by_id["canton_http_zh"]["notes"]).lower()
    assert by_id["canton_http_zh"]["acquisition_readiness"] == "scaffold"
    assert "needs engineering" in scaffold_notes
    # A scaffold must never be described as ready to gather evidence.
    assert "acceptance harness" not in scaffold_notes

    awaiting = by_id["ch_court_decisions_bger"]
    awaiting_notes = " ".join(awaiting["notes"]).lower()
    assert awaiting["acquisition_readiness"] == "awaiting_evidence"
    assert "implemented and verified" in awaiting_notes
    assert "acceptance harness" in awaiting_notes
    # …and must never be sent to an engineer, which is the whole point.
    assert "needs engineering" not in awaiting_notes

    # The boolean projection stays consistent with the enum on every row.
    for row in rows:
        assert row["live_ready"] is (row["acquisition_readiness"] == "live")


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
    # The detail must name the remedy, not just the refusal. canton_http genuinely
    # needs engineering — though note its start_run IS implemented and inherited;
    # `scaffold` is remedy-shaped, so the message says "cannot acquire its targets"
    # rather than asserting a stub the code contradicts (#743).
    assert "cannot acquire its targets" in lock.detail.lower()
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
    # general way past the code key. Open the config key so the code key is what
    # refuses — otherwise the config key refuses first and this proves nothing
    # about the scaffold.
    source, version = await _approved_version_from_template(session, SCAFFOLD_TEMPLATE)
    await BlueprintEnablementService(session).set_enabled(
        *SCAFFOLD_TEMPLATE, enabled=True, note="flip", actor="op_local_dev"
    )
    await session.commit()
    run_service = RunService(session, provider_registry=build_provider_registry(_settings()))

    readiness = await run_service.get_run_readiness(
        source_id=source.source_id,
        source_version_id=version.source_version_id,
        mode=RunMode.ACCEPTANCE,
    )
    lock = next(c for c in readiness.checks if c.code == "acquisition_lock_open")
    assert lock.ok is False
    assert "cannot acquire its targets" in lock.detail.lower()
    assert "needs engineering" in lock.detail.lower()


@pytest.mark.asyncio
async def test_acceptance_does_not_override_an_operator_disabling_a_live_template(session) -> None:
    """The config key stays a kill switch, for every provider (#743 review).

    An operator override is the only audited way to stop traffic at one portal
    without a deploy — what you reach for when an authority complains about load.
    A waiver that ignored it would make the switch advisory.

    The reason this holds is narrower than it was before #768. It is not "the
    provider is LIVE, so its operator can simply turn the key" — that reasoning
    was wrong, and #768 is what it cost: it also locked out every never-turned
    key on a LIVE provider, whose operator could *not* simply turn it without
    the evidence the lock demanded. What is load-bearing is that the key was
    **explicitly closed**. See
    `test_acceptance_is_admitted_for_a_never_turned_key_on_a_live_provider` for
    the other side of that line.
    """
    source, version = await _approved_version_from_template(session, LIVE_TEMPLATE)
    await BlueprintEnablementService(session).set_enabled(
        *LIVE_TEMPLATE, enabled=False, note="STOP: authority complained about load", actor="op_x"
    )
    await session.commit()

    run_service = RunService(session, provider_registry=build_provider_registry(_settings()))
    readiness = await run_service.get_run_readiness(
        source_id=source.source_id,
        source_version_id=version.source_version_id,
        mode=RunMode.ACCEPTANCE,
    )
    lock = next(c for c in readiness.checks if c.code == "acquisition_lock_open")
    assert lock.ok is False
    assert "config key closed" in lock.detail.lower()

    # And the enforcement path agrees — not just its pre-flight mirror.
    provider = run_service._resolve_provider_for_source_version(version)
    with pytest.raises(BlueprintTemplateNotEnabledError):
        await run_service._require_launchable(version, provider, RunMode.ACCEPTANCE)


@pytest.mark.asyncio
async def test_acceptance_refuses_a_template_deleted_from_the_shipped_blueprints(session) -> None:
    # Deleting a template from source_blueprints.yaml is the deploy-time way to
    # stop crawling a portal. The waiver is about the `enabled` flag alone, so a
    # version pointing at a template that no longer exists must still refuse.
    source, version = await _approved_version_from_template(session, AWAITING_EVIDENCE_TEMPLATE)
    version.provider_template_id = "gone_from_the_shipped_blueprints"
    await session.commit()

    run_service = RunService(session, provider_registry=build_provider_registry(_settings()))
    provider = run_service._resolve_provider_for_source_version(version)
    with pytest.raises(NotFoundError):
        await run_service._require_launchable(version, provider, RunMode.ACCEPTANCE)


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
    # Since #735 this provider's readiness is `live`; the note now points at the
    # remaining config key rather than at missing evidence.
    assert any("readiness=live" in note for note in plan_notes)


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


@pytest.mark.asyncio
async def test_create_run_enforces_the_lock_not_just_the_preflight(session) -> None:
    """`create_run`, not `get_run_readiness` (#743 review).

    The original tests for the acceptance exemption only called
    `get_run_readiness`, which exercises `_assess_launch_lock` — the *mirror* of
    the lock, not the lock. A reviewer proved it: reverting
    `for_acceptance = run_mode is RunMode.ACCEPTANCE` in `_require_launchable`
    left 518 tests green. The two diverging is exactly the #634 defect the
    method's own docstring warns about, so the enforcement path needs its own
    assertions.
    """
    source, version = await _approved_version_from_template(session, AWAITING_EVIDENCE_TEMPLATE)
    # `_approved_version_from_template` does not actually approve, and an
    # unapproved version is refused by `_validate_version_for_run_mode` BEFORE the
    # lock is reached — so without this the production assertion below would pass
    # for the wrong reason and prove nothing about the lock.
    version.status = SourceVersionStatus.APPROVED
    await session.commit()
    run_service = RunService(session, provider_registry=build_provider_registry(_settings()))

    # Production is refused on the config key by the enforcement path itself.
    with pytest.raises(BlueprintTemplateNotEnabledError):
        await run_service.create_run(
            CreateRunRequest(
                source_id=source.source_id,
                source_version_id=version.source_version_id,
                mode=RunMode.PRODUCTION,
            )
        )

    # Acceptance is admitted all the way through run creation, on a template
    # whose config key is shut — that is the deadlock break, enforced.
    run = await run_service.create_run(
        CreateRunRequest(
            source_id=source.source_id,
            source_version_id=version.source_version_id,
            mode=RunMode.ACCEPTANCE,
        )
    )
    assert run.mode is RunMode.ACCEPTANCE
    # Persisted, so the dispatch-time re-check sees the same value the request
    # carried and the evidence stays self-labelling.
    assert run.run_id


@pytest.mark.asyncio
async def test_create_run_refuses_acceptance_for_a_scaffold(session) -> None:
    # The exemption must not become a general way past the code key, asserted on
    # the enforcement path rather than the mirror.
    source, version = await _approved_version_from_template(session, SCAFFOLD_TEMPLATE)
    version.status = SourceVersionStatus.APPROVED
    await BlueprintEnablementService(session).set_enabled(
        *SCAFFOLD_TEMPLATE, enabled=True, note="flip", actor="op_local_dev"
    )
    await session.commit()
    run_service = RunService(session, provider_registry=build_provider_registry(_settings()))

    # Both keys would otherwise be open; the code key alone must refuse.
    with pytest.raises(ProviderNotLiveReadyError):
        await run_service.create_run(
            CreateRunRequest(
                source_id=source.source_id,
                source_version_id=version.source_version_id,
                mode=RunMode.ACCEPTANCE,
            )
        )


@pytest.mark.asyncio
async def test_readiness_reports_an_unknown_provider_instead_of_500ing(session) -> None:
    # Regression guard (#743 review round 2). Moving provider resolution ahead of
    # the config-key check made `ProviderRegistry.get`'s KeyError reachable from
    # the readiness endpoint, where the config-key branch used to answer first.
    # Readiness is a read-only pre-flight; an unknown provider is a closed key,
    # not a 500.
    source, version = await _approved_version_from_template(session, LIVE_TEMPLATE)
    version.acquisition_spec = {**(version.acquisition_spec or {}), "provider": "no_such_provider"}
    await session.commit()

    run_service = RunService(session, provider_registry=build_provider_registry(_settings()))
    readiness = await run_service.get_run_readiness(
        source_id=source.source_id,
        source_version_id=version.source_version_id,
        mode=RunMode.PRODUCTION,
    )
    lock = next(c for c in readiness.checks if c.code == "acquisition_lock_open")
    assert lock.ok is False
    assert "unknown provider" in lock.detail.lower()


@pytest.mark.asyncio
async def test_a_failing_acceptance_run_is_not_retried_forever(session) -> None:
    """A rehearsal must be one-shot even when dispatch throws (#743 review round 3).

    A fresh reviewer demonstrated this against running code: an acceptance run
    whose `start_run` raises (portal timeout, 5xx) stays PENDING, is re-dispatched
    every poll cycle, and — because the acceptance waiver skips the config key —
    the operator's `enabled: false` kill switch does not stop it. Three portal
    hits landed after the switch was thrown. That is a second route to unattended
    repetition beside the schedule ban ADR-0030 §6 relies on.
    """

    class _ExplodingProvider:
        provider_name = "gemeinde_http"
        readiness = AcquisitionReadiness.AWAITING_EVIDENCE
        calls = 0

        async def start_run(self, source, source_version, run):
            type(self).calls += 1
            raise RuntimeError("portal timed out")

    source, version = await _approved_version_from_template(session, AWAITING_EVIDENCE_TEMPLATE)
    version.status = SourceVersionStatus.APPROVED
    await session.commit()

    provider = _ExplodingProvider()
    service = RunService(session, provider=provider, run_dispatch_backend="worker")
    run = await service.create_run(
        CreateRunRequest(
            source_id=source.source_id,
            source_version_id=version.source_version_id,
            mode=RunMode.ACCEPTANCE,
        )
    )
    assert run.status is RunStatus.PENDING

    await service.dispatch_pending_runs()
    await session.refresh(run)
    # Terminal, so no later poll cycle can pick it up again.
    assert run.status is RunStatus.FAILED
    assert "not retried" in (run.failure_reason or "")

    calls_after_first = _ExplodingProvider.calls
    await service.dispatch_pending_runs()
    assert _ExplodingProvider.calls == calls_after_first


@pytest.mark.asyncio
async def test_acceptance_is_admitted_for_a_never_turned_key_on_a_live_provider(session) -> None:
    """The #768 deadlock: a new template on a provider already promoted to LIVE.

    Before this, the waiver keyed off *provider* readiness, so a LIVE provider's
    templates could never be acceptance-run while shut. The refusal told the
    operator to "capture acceptance-run evidence, then enable it" — and the same
    check is what forbade the acceptance run. The instruction was impossible to
    follow, and the only exits were flipping the key blind or editing code.

    This is the common case as coverage extends along an axis (#584, #731, #736):
    same proven provider, new template.
    """
    source, version = await _approved_version_from_template(session, LIVE_BUT_SHUT_TEMPLATE)
    run_service = RunService(session, provider_registry=build_provider_registry(_settings()))

    # Production is still refused — the config key is genuinely shut.
    production = await run_service.get_run_readiness(
        source_id=source.source_id,
        source_version_id=version.source_version_id,
        mode=RunMode.PRODUCTION,
    )
    production_lock = next(c for c in production.checks if c.code == "acquisition_lock_open")
    assert production_lock.ok is False
    assert "config key closed" in production_lock.detail.lower()
    # And it must name the remedy that is actually available.
    assert "acceptance" in production_lock.detail.lower()

    # Acceptance is admitted, so the evidence can be earned.
    acceptance = await run_service.get_run_readiness(
        source_id=source.source_id,
        source_version_id=version.source_version_id,
        mode=RunMode.ACCEPTANCE,
    )
    acceptance_lock = next(c for c in acceptance.checks if c.code == "acquisition_lock_open")
    assert acceptance_lock.ok is True
    assert "never been turned" in acceptance_lock.detail.lower()
    # A pass must not read as "the keys are turned".
    assert "not a production run" in acceptance_lock.detail.lower()

    # The enforcement path agrees with its pre-flight mirror — the #634 divergence.
    provider = run_service._resolve_provider_for_source_version(version)
    await run_service._require_launchable(version, provider, RunMode.ACCEPTANCE)


@pytest.mark.asyncio
async def test_an_operator_reclosing_a_key_still_blocks_acceptance_on_a_live_provider(
    session,
) -> None:
    """The kill switch survives #768 for the template that motivated it.

    The waiver turns on *how* the key came to be shut, so the same template that
    earns acceptance while never-turned must lose it the moment an operator
    closes it deliberately. Without this, #768's fix would have quietly widened
    into the blanket waiver the pre-#768 code was right to refuse.
    """
    source, version = await _approved_version_from_template(session, LIVE_BUT_SHUT_TEMPLATE)
    # Turn it on, then off — the second flip is a deliberate close, not a default.
    enablement = BlueprintEnablementService(session)
    await enablement.set_enabled(
        *LIVE_BUT_SHUT_TEMPLATE, enabled=True, note="acceptance evidence captured", actor="op_x"
    )
    await enablement.set_enabled(
        *LIVE_BUT_SHUT_TEMPLATE,
        enabled=False,
        note="STOP: authority complained about load",
        actor="op_x",
    )
    await session.commit()

    run_service = RunService(session, provider_registry=build_provider_registry(_settings()))
    readiness = await run_service.get_run_readiness(
        source_id=source.source_id,
        source_version_id=version.source_version_id,
        mode=RunMode.ACCEPTANCE,
    )
    lock = next(c for c in readiness.checks if c.code == "acquisition_lock_open")
    assert lock.ok is False
    # And the remedy must name the switch, not send the operator to capture
    # evidence they already have.
    assert "operator turned this key off" in lock.detail.lower()
    assert "capture acceptance-run evidence" not in lock.detail.lower()

    provider = run_service._resolve_provider_for_source_version(version)
    with pytest.raises(BlueprintTemplateNotEnabledError):
        await run_service._require_launchable(version, provider, RunMode.ACCEPTANCE)


@pytest.mark.asyncio
async def test_a_waived_config_key_never_admits_a_scaffold(session) -> None:
    """The config-key waiver must not leak into the code key.

    #768 widened when the config key is waived; the code key is untouched. A
    scaffold provider cannot acquire anything, so admitting it would send a run
    at a live portal with no implementation behind it.
    """
    source, version = await _approved_version_from_template(session, SCAFFOLD_TEMPLATE)
    run_service = RunService(session, provider_registry=build_provider_registry(_settings()))

    readiness = await run_service.get_run_readiness(
        source_id=source.source_id,
        source_version_id=version.source_version_id,
        mode=RunMode.ACCEPTANCE,
    )
    lock = next(c for c in readiness.checks if c.code == "acquisition_lock_open")
    assert lock.ok is False
    assert "code key closed" in lock.detail.lower()
    assert "needs engineering" in lock.detail.lower()
