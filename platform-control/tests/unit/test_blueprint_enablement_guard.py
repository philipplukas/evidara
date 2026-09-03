"""The server-side ADR-0030 config-key guard (#854, #846).

Every refusal here has its own test, and each test fails when its check is removed —
that is the standard the CLI's five guards were held to and this is the same guard,
moved to where both clients meet it.

The two defects being closed:

- **#854** — the admin panel armed the config key on a non-empty free-text note and
  nothing else, while `evidara workflow coverage enable` required a cited acceptance
  run and refused with eight named codes. The easier path was the weaker one, so the
  CLI's guard was advisory.
- **#846** — the CLI bound cited evidence to the template's *acquisition provider*.
  All 26 cantons and Bund sit behind the single `lexfind` provider, so one passing run
  for any canton satisfied the check for every LexFind template.
"""

from __future__ import annotations

import pytest

from platform_control.domain import ExecutionMode, RunMode, RunStatus
from platform_control.errors import NotFoundError
from platform_control.models.authority import Authority, Jurisdiction
from platform_control.models.run import Run
from platform_control.schemas.source import CreateSourceRequest, CreateSourceVersionRequest
from platform_control.services.blueprint_enablement import (
    BlueprintEnablementGuard,
    BlueprintEnablementService,
)
from platform_control.services.blueprint_enablement_guard import (
    BINDING_ACQUISITION_SPEC,
    BINDING_NONE,
    BINDING_PROVIDER,
    BINDING_TEMPLATE,
    AcceptanceVerdict,
    EvidenceBinding,
    acceptance_evidence_verdict,
    evidence_binding,
    flip_verdict,
    read_back_problems,
)
from platform_control.services.source_service import SourceService

# Two LexFind templates that differ only in their search scope, both behind the one
# `lexfind_api` provider — the exact pair #846 says must not share evidence.
BE_TEMPLATE = ("ch", "lexfind_api_be_hunde")
BS_TEMPLATE = ("ch", "lexfind_api_bs_hunde")
# A provider whose code key is still below `live`, so the ordering rule bites.
AWAITING_EVIDENCE_TEMPLATE = ("ch", "ch_court_decisions_bger")


def _codes(refusals) -> list[str]:
    return [item.code for item in refusals]


# ---------------------------------------------------------------------------------
# Pure verdict functions — one test per refusal
# ---------------------------------------------------------------------------------


def _passing_evidence() -> tuple[AcceptanceVerdict, EvidenceBinding]:
    verdict = acceptance_evidence_verdict(
        run_id="run_1",
        refused=False,
        status="completed",
        mode="acceptance",
        execution_mode="live",
        captured_resources_count=4,
    )
    assert verdict.is_acceptance_evidence
    return verdict, EvidenceBinding(strength=BINDING_TEMPLATE)


def _verdict(**overrides):
    verdict, binding = _passing_evidence()
    kwargs = {
        "desired_enabled": True,
        "note": "acceptance bundle 2026-07-28",
        "readiness": "live",
        "config_key_provenance": "default",
        "evidence_run_id": "run_1",
        "evidence_run_exists": True,
        "acceptance": verdict,
        "binding": binding,
        "reopen_operator_kill_switch": False,
        "acknowledge_provider_below_live": False,
    }
    kwargs.update(overrides)
    return flip_verdict(**kwargs)


def test_the_happy_path_refuses_nothing_and_wants_no_human() -> None:
    """The control: without this, every test below could pass on a guard that always refuses."""
    decision = _verdict()
    assert decision.refusals == []
    assert decision.needs_human is False


def test_a_flip_with_no_note_is_refused_in_both_directions() -> None:
    assert _codes(_verdict(note="   ").refusals) == ["no_audit_note_recorded"]
    # Closing the key needs no evidence — it can only reduce what dispatches — but it
    # still has to say why. #854: turning it off used to require nothing at all.
    closing = _verdict(desired_enabled=False, note=None, evidence_run_id=None, acceptance=None)
    assert _codes(closing.refusals) == ["no_audit_note_recorded"]


def test_closing_the_key_needs_no_evidence() -> None:
    closing = _verdict(
        desired_enabled=False,
        note="shut pending terms review",
        evidence_run_id=None,
        evidence_run_exists=False,
        acceptance=None,
        binding=None,
        readiness="scaffold",
        config_key_provenance="override",
    )
    assert closing.refusals == []


def test_enabling_without_a_cited_run_is_refused() -> None:
    decision = _verdict(evidence_run_id=None, acceptance=None, binding=None)
    assert _codes(decision.refusals) == ["no_evidence_run_cited"]


def test_a_cited_run_that_does_not_exist_is_refused() -> None:
    decision = _verdict(evidence_run_exists=False, acceptance=None, binding=None)
    assert _codes(decision.refusals) == ["evidence_run_not_found"]


@pytest.mark.parametrize(
    ("overrides", "expected"),
    [
        ({"refused": True}, "run_refused_by_lock"),
        ({"status": "failed"}, "run_not_completed"),
        ({"mode": "production"}, "mode_not_acceptance"),
        ({"execution_mode": "shadow"}, "execution_mode_shadow"),
        ({"captured_resources_count": 0}, "no_captured_resources"),
    ],
)
def test_each_acceptance_rule_disqualifies_a_run(overrides: dict, expected: str) -> None:
    """ADR-0030 §2/§6. `execution_mode_shadow` is the one that looks greenest."""
    kwargs = {
        "run_id": "run_1",
        "refused": False,
        "status": "completed",
        "mode": "acceptance",
        "execution_mode": "live",
        "captured_resources_count": 4,
    }
    kwargs.update(overrides)
    verdict = acceptance_evidence_verdict(**kwargs)
    assert verdict.is_acceptance_evidence is False
    assert expected in _codes(verdict.refusals)

    decision = _verdict(acceptance=verdict)
    assert "evidence_run_is_not_acceptance_evidence" in _codes(decision.refusals)


def test_a_run_with_no_capture_count_refuses_rather_than_skipping_the_check() -> None:
    """#744: a check that cannot run must refuse, not pass."""
    verdict = acceptance_evidence_verdict(
        run_id="run_1",
        refused=False,
        status="completed",
        mode="acceptance",
        execution_mode="live",
        captured_resources_count=None,
    )
    # The count being absent is not itself an acceptance failure — it is a check that
    # did not run, and the flip guard is what refuses on it.
    assert verdict.is_acceptance_evidence is True
    assert _codes(_verdict(acceptance=verdict).refusals) == ["evidence_run_capture_count_unknown"]


def test_a_provider_below_live_is_refused_unless_acknowledged() -> None:
    assert _codes(_verdict(readiness="awaiting_evidence").refusals) == [
        "provider_not_live_not_acknowledged"
    ]
    armed = _verdict(readiness="awaiting_evidence", acknowledge_provider_below_live=True)
    assert armed.refusals == []
    assert armed.needs_human is True


def test_an_operator_kill_switch_is_refused_unless_acknowledged() -> None:
    """#768: `enabled: false, source: override` is a deliberate act, not an unearned key."""
    assert _codes(_verdict(config_key_provenance="override").refusals) == [
        "operator_kill_switch_not_acknowledged"
    ]
    reopened = _verdict(config_key_provenance="override", reopen_operator_kill_switch=True)
    assert reopened.refusals == []
    assert reopened.needs_human is True


def test_a_scaffold_provider_does_not_mask_a_closed_key() -> None:
    """Every check keys off the *states*, never off one priority-ordered blocker value."""
    decision = _verdict(readiness="scaffold", config_key_provenance="override")
    assert _codes(decision.refusals) == [
        "provider_not_live_not_acknowledged",
        "operator_kill_switch_not_acknowledged",
    ]


# --- Evidence binding (#846) ------------------------------------------------------


def _bind(**overrides) -> EvidenceBinding:
    kwargs = {
        "template_overlay_id": "ch",
        "template_provider_template_id": "lexfind_api_be_hunde",
        "template_provider": "lexfind_api",
        "template_spec": {"provider": "lexfind_api", "search_text": "Hund", "entity_ids": [4]},
        "version_overlay_id": "ch",
        "version_provider_template_id": "lexfind_api_be_hunde",
        "version_spec": {"provider": "lexfind_api", "search_text": "Hund", "entity_ids": [4]},
    }
    kwargs.update(overrides)
    return evidence_binding(**kwargs)


def test_a_version_recording_this_template_binds_exactly() -> None:
    binding = _bind()
    assert binding.strength == BINDING_TEMPLATE
    assert binding.refusal_code is None
    assert _verdict(binding=binding).needs_human is False


def test_a_version_with_no_provider_cannot_bind() -> None:
    binding = _bind(version_spec={})
    assert binding.strength == BINDING_NONE
    assert binding.refusal_code == "evidence_run_provider_unresolved"
    assert _codes(_verdict(binding=binding).refusals) == ["evidence_run_provider_unresolved"]


def test_a_run_on_another_provider_cannot_bind() -> None:
    binding = _bind(version_spec={"provider": "fedlex_sparql"})
    assert binding.strength == BINDING_NONE
    assert binding.refusal_code == "evidence_run_provider_mismatch"
    assert _codes(_verdict(binding=binding).refusals) == ["evidence_run_provider_mismatch"]


def test_a_same_provider_run_of_another_template_is_refused() -> None:
    """#846's core: one canton's LexFind run must not arm another canton's template."""
    binding = _bind(version_provider_template_id="lexfind_api_bs_hunde")
    assert binding.strength == BINDING_PROVIDER
    assert binding.refusal_code == "evidence_run_template_mismatch"
    assert binding.bound_provider_template_id == "lexfind_api_bs_hunde"
    assert _codes(_verdict(binding=binding).refusals) == ["evidence_run_template_mismatch"]


def test_a_version_with_no_provenance_binds_by_spec_equality_and_wants_a_human() -> None:
    """The `blueprint-preview` comparison #846 proposed, as the fallback path."""
    binding = _bind(version_overlay_id=None, version_provider_template_id=None)
    assert binding.strength == BINDING_ACQUISITION_SPEC
    assert binding.refusal_code is None
    decision = _verdict(binding=binding)
    assert decision.refusals == []
    assert decision.needs_human is True
    assert "acquisition-spec equality" in decision.needs_human_reasons[0]


def test_a_version_with_no_provenance_and_a_different_spec_is_refused() -> None:
    binding = _bind(
        version_overlay_id=None,
        version_provider_template_id=None,
        version_spec={"provider": "lexfind_api", "search_text": "Hund", "entity_ids": [6]},
    )
    assert binding.strength == BINDING_PROVIDER
    assert binding.refusal_code == "evidence_run_template_unbindable"
    assert _codes(_verdict(binding=binding).refusals) == ["evidence_run_template_unbindable"]


# --- Read-back --------------------------------------------------------------------


def test_the_read_back_requires_both_the_value_and_the_provenance() -> None:
    """#631/#713: either signal alone is also satisfied by a write that did nothing."""
    assert (
        read_back_problems(effective_enabled=True, provenance="override", desired_enabled=True)
        == []
    )
    assert _codes(
        read_back_problems(effective_enabled=False, provenance="override", desired_enabled=True)
    ) == ["read_back_disagrees"]
    assert _codes(
        read_back_problems(effective_enabled=True, provenance="default", desired_enabled=True)
    ) == ["no_override_recorded"]


# ---------------------------------------------------------------------------------
# The guard against a real session
# ---------------------------------------------------------------------------------


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


async def _acceptance_run(
    session,
    template: tuple[str, str],
    *,
    run_id: str,
    execution_mode: ExecutionMode = ExecutionMode.LIVE,
    status: RunStatus = RunStatus.COMPLETED,
    mode: RunMode = RunMode.ACCEPTANCE,
    captured: int = 4,
) -> Run:
    """A completed acceptance run whose version was created from ``template``."""
    source_service = SourceService(session)
    source = await source_service.create_source(
        CreateSourceRequest(
            name=f"{template[1]} source",
            jurisdiction_id="jur_ch_federal",
            authority_id="auth_fedlex",
        )
    )
    version = await source_service.create_source_version(
        source.source_id,
        CreateSourceVersionRequest(
            version_label="v1",
            overlay_id=template[0],
            provider_template_id=template[1],
            execution_mode=execution_mode,
        ),
    )
    run = Run(
        run_id=run_id,
        source_id=source.source_id,
        source_version_id=version.source_version_id,
        mode=mode,
        status=status,
        captured_resources_count=captured,
    )
    session.add(run)
    await session.commit()
    return run


@pytest.mark.asyncio
async def test_a_note_alone_no_longer_arms_the_config_key(session) -> None:
    """#854: this exact payload is what the admin dialog sent, and it flipped the key."""
    await _seed_reference(session)
    outcome = await BlueprintEnablementGuard(session).flip(
        *BE_TEMPLATE,
        enabled=True,
        note="looks fine to me",
        actor="op_local_dev",
    )
    assert outcome.refused is True
    assert _codes(outcome.refusals) == ["no_evidence_run_cited"]
    assert outcome.write_attempted is False
    # Nothing was written: the key is still on its shipped default.
    state = await BlueprintEnablementService(session).get_state(*BE_TEMPLATE)
    assert state.enabled is False
    assert state.source == "default"


@pytest.mark.asyncio
async def test_evidence_from_one_lexfind_canton_does_not_enable_another(session) -> None:
    """#846's acceptance criterion, end to end against the shipped blueprints.

    `lexfind_api_be_hunde` and `lexfind_api_bs_hunde` differ only in the entity they
    search, and both sit behind the one `lexfind_api` provider. Under the CLI's
    provider-level binding, BE's run armed BS.
    """
    await _seed_reference(session)
    await _acceptance_run(session, BE_TEMPLATE, run_id="run_be_acceptance")
    guard = BlueprintEnablementGuard(session)

    stolen = await guard.flip(
        *BS_TEMPLATE,
        enabled=True,
        note="BE bundle 2026-07-28",
        evidence_run_id="run_be_acceptance",
        actor="op_local_dev",
    )
    assert _codes(stolen.refusals) == ["evidence_run_template_mismatch"]
    assert stolen.evidence_binding == BINDING_PROVIDER
    assert (await BlueprintEnablementService(session).get_state(*BS_TEMPLATE)).enabled is False

    # The same run does arm its own template, and binds exactly.
    earned = await guard.flip(
        *BE_TEMPLATE,
        enabled=True,
        note="BE bundle 2026-07-28",
        evidence_run_id="run_be_acceptance",
        actor="op_local_dev",
    )
    assert earned.refusals == []
    assert earned.evidence_binding == BINDING_TEMPLATE
    assert earned.applied is True
    assert earned.needs_human is False
    after = await BlueprintEnablementService(session).get_state(*BE_TEMPLATE)
    assert after.enabled is True
    assert after.source == "override"


@pytest.mark.asyncio
async def test_a_shadow_run_never_arms_the_key(session) -> None:
    """ADR-0030 §2: a SHADOW version replays fixtures and never meets the portal."""
    await _seed_reference(session)
    await _acceptance_run(
        session, BE_TEMPLATE, run_id="run_shadow", execution_mode=ExecutionMode.SHADOW
    )
    outcome = await BlueprintEnablementGuard(session).flip(
        *BE_TEMPLATE,
        enabled=True,
        note="shadow run looked green",
        evidence_run_id="run_shadow",
        actor="op_local_dev",
    )
    assert _codes(outcome.refusals) == ["evidence_run_is_not_acceptance_evidence"]
    assert _codes(outcome.acceptance_verdict.refusals) == ["execution_mode_shadow"]
    assert (await BlueprintEnablementService(session).get_state(*BE_TEMPLATE)).enabled is False


@pytest.mark.asyncio
async def test_an_operator_kill_switch_is_not_reopened_silently(session) -> None:
    await _seed_reference(session)
    await _acceptance_run(session, BE_TEMPLATE, run_id="run_be_acceptance")
    guard = BlueprintEnablementGuard(session)

    shut = await guard.flip(
        *BE_TEMPLATE, enabled=False, note="terms unconfirmed", actor="op_local_dev"
    )
    assert shut.refusals == []
    assert shut.applied is True

    blocked = await guard.flip(
        *BE_TEMPLATE,
        enabled=True,
        note="BE bundle 2026-07-28",
        evidence_run_id="run_be_acceptance",
        actor="op_other",
    )
    assert _codes(blocked.refusals) == ["operator_kill_switch_not_acknowledged"]
    assert (await BlueprintEnablementService(session).get_state(*BE_TEMPLATE)).enabled is False

    reopened = await guard.flip(
        *BE_TEMPLATE,
        enabled=True,
        note="BE bundle 2026-07-28; agreed with the operator who shut it",
        evidence_run_id="run_be_acceptance",
        reopen_operator_kill_switch=True,
        actor="op_other",
    )
    assert reopened.refusals == []
    assert reopened.needs_human is True


@pytest.mark.asyncio
async def test_a_provider_below_live_is_not_armed_unacknowledged(session) -> None:
    await _seed_reference(session)
    await _acceptance_run(session, AWAITING_EVIDENCE_TEMPLATE, run_id="run_bger_acceptance")
    guard = BlueprintEnablementGuard(session)

    blocked = await guard.flip(
        *AWAITING_EVIDENCE_TEMPLATE,
        enabled=True,
        note="bger acceptance bundle",
        evidence_run_id="run_bger_acceptance",
        actor="op_local_dev",
    )
    assert _codes(blocked.refusals) == ["provider_not_live_not_acknowledged"]

    armed = await guard.flip(
        *AWAITING_EVIDENCE_TEMPLATE,
        enabled=True,
        note="bger acceptance bundle; code key request filed",
        evidence_run_id="run_bger_acceptance",
        acknowledge_provider_below_live=True,
        actor="op_local_dev",
    )
    assert armed.refusals == []
    assert armed.needs_human is True
    assert "ahead of the code key" in armed.needs_human_reasons[0]


@pytest.mark.asyncio
async def test_a_cited_run_that_does_not_exist_writes_nothing(session) -> None:
    await _seed_reference(session)
    outcome = await BlueprintEnablementGuard(session).flip(
        *BE_TEMPLATE,
        enabled=True,
        note="citing a run id I typed from memory",
        evidence_run_id="run_does_not_exist",
        actor="op_local_dev",
    )
    assert _codes(outcome.refusals) == ["evidence_run_not_found"]
    assert (await BlueprintEnablementService(session).get_state(*BE_TEMPLATE)).enabled is False


@pytest.mark.asyncio
async def test_an_unknown_template_is_a_bad_reference_not_a_refusal(session) -> None:
    await _seed_reference(session)
    with pytest.raises(NotFoundError):
        await BlueprintEnablementGuard(session).flip(
            "ch",
            "no_such_template",
            enabled=False,
            note="typo",
            actor="op_local_dev",
        )
