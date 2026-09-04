from __future__ import annotations

import json
from typing import Any
from unittest.mock import patch

import pytest
import typer
from typer.testing import CliRunner

from evidara_cli.client import HttpJsonError
from evidara_cli.coverage import (
    STALL_NO_DISPATCH_WORKER,
    STALL_PUBLISH_PATH_DISABLED,
    STALL_RUN_REFUSED,
)
from evidara_cli.coverage_cmd import (
    coverage_enable,
    coverage_preflight,
    coverage_templates,
    coverage_watch,
)
from evidara_cli.main import app

TEMPLATES = {
    "data": [
        {
            "overlay_id": "ch",
            "provider_template_id": "fedlex_sparql_constitution_de",
            "provider": "fedlex_sparql",
            "acquisition_readiness": "live",
            "enabled": True,
            "source": "default",
            "launchable": True,
            "notes": [],
        },
        {
            "overlay_id": "ch",
            "provider_template_id": "lexfind_zh_hundegesetz",
            "provider": "lexfind",
            "acquisition_readiness": "awaiting_evidence",
            "enabled": False,
            "source": "default",
            "launchable": False,
            "notes": ["Code key closed: no acceptance-run evidence yet."],
        },
        {
            "overlay_id": "at",
            "provider_template_id": "ris_ogd_bundesrecht",
            "provider": "ris_ogd",
            "acquisition_readiness": "scaffold",
            "enabled": False,
            "source": "default",
            "launchable": False,
            "notes": ["Code key closed: provider is a scaffold."],
        },
    ]
}


def _payload(emit_mock: Any) -> dict[str, Any]:
    emit_mock.assert_called_once()
    return emit_mock.call_args.args[0]


# --- templates ---------------------------------------------------------------------


@patch("evidara_cli.coverage_cmd._emit")
@patch("evidara_cli.coverage_cmd.request_json", return_value=TEMPLATES)
@patch("evidara_cli.coverage_cmd.platform_control_base_url", return_value="http://pc.test")
def test_templates_classifies_every_row(_base: object, _req: object, emit_mock: Any) -> None:
    coverage_templates(
        overlay=None,
        provider=None,
        template=None,
        readiness=None,
        blocker=None,
        mode=None,
        human=False,
        correlation_id=None,
    )
    payload = _payload(emit_mock)
    assert payload["ok"] is True
    assert payload["workflow"] == "coverage-loop"
    summary = payload["artifacts"]["summary"]
    assert summary["total"] == 3
    assert summary["launchable"] == 1
    assert summary["acceptance_ready"] == 2
    assert summary["needs_engineering"] == 1


@patch("evidara_cli.coverage_cmd._emit")
@patch("evidara_cli.coverage_cmd.request_json", return_value=TEMPLATES)
@patch("evidara_cli.coverage_cmd.platform_control_base_url", return_value="http://pc.test")
def test_templates_filters_to_what_an_operator_can_unblock_today(
    _base: object, _req: object, emit_mock: Any
) -> None:
    coverage_templates(
        overlay=None,
        provider=None,
        template=None,
        readiness=None,
        blocker="provider_awaiting_evidence",
        mode=None,
        human=False,
        correlation_id=None,
    )
    rows = _payload(emit_mock)["artifacts"]["templates"]
    assert [r["provider_template_id"] for r in rows] == ["lexfind_zh_hundegesetz"]
    assert rows[0]["remedy"] == "run_acceptance_loop"


@patch("evidara_cli.coverage_cmd._emit")
@patch("evidara_cli.coverage_cmd.request_json", return_value=TEMPLATES)
@patch("evidara_cli.coverage_cmd.platform_control_base_url", return_value="http://pc.test")
def test_templates_mode_filter_selects_dispatchable_templates(
    _base: object, _req: object, emit_mock: Any
) -> None:
    coverage_templates(
        overlay=None,
        provider=None,
        template=None,
        readiness=None,
        blocker=None,
        mode="production",
        human=False,
        correlation_id=None,
    )
    rows = _payload(emit_mock)["artifacts"]["templates"]
    assert [r["provider_template_id"] for r in rows] == ["fedlex_sparql_constitution_de"]


@patch("evidara_cli.coverage_cmd._emit")
@patch("evidara_cli.coverage_cmd.platform_control_base_url", return_value="http://pc.test")
def test_templates_fails_loudly_when_it_disagrees_with_the_server(
    _base: object, emit_mock: Any
) -> None:
    drifted = {
        "data": [
            {
                **TEMPLATES["data"][2],
                # Server says launchable; the code key says scaffold. One of us is wrong.
                "launchable": True,
            }
        ]
    }
    with patch("evidara_cli.coverage_cmd.request_json", return_value=drifted):
        with pytest.raises(typer.Exit) as exc:
            coverage_templates(
                overlay=None,
                provider=None,
                template=None,
                readiness=None,
                blocker=None,
                mode=None,
                human=False,
                correlation_id=None,
            )
    assert exc.value.exit_code == 1
    payload = _payload(emit_mock)
    assert payload["ok"] is False
    assert payload["artifacts"]["summary"]["disagreements_with_server"] == 1


# --- preflight ---------------------------------------------------------------------


@patch("evidara_cli.coverage_cmd._emit")
@patch("evidara_cli.coverage_cmd.request_status", return_value=200)
@patch("evidara_cli.coverage_cmd.request_json")
@patch("evidara_cli.coverage_cmd.legal_search_base_url", return_value="http://ls.test")
@patch("evidara_cli.coverage_cmd.platform_control_base_url", return_value="http://pc.test")
def test_preflight_recommends_acceptance_for_a_provider_awaiting_evidence(
    _pc: object, _ls: object, req_mock: Any, _status: object, emit_mock: Any
) -> None:
    req_mock.side_effect = [
        TEMPLATES,
        {"acquisition_spec": {"provider": "lexfind"}, "plan_notes": ["Would fetch tol/22871"]},
    ]
    coverage_preflight(
        overlay="ch",
        template="lexfind_zh_hundegesetz",
        check_search=True,
        human=False,
        correlation_id=None,
    )
    payload = _payload(emit_mock)
    assert payload["ok"] is True
    assert payload["artifacts"]["template"]["recommended_mode"] == "acceptance"
    assert "--mode acceptance" in payload["artifacts"]["next_command"]
    assert payload["artifacts"]["plan_notes"] == ["Would fetch tol/22871"]
    # A rehearsal must never read as an open lock (ADR-0030 §6).
    assert "does NOT imply" in payload["artifacts"]["acceptance_note"]


@patch("evidara_cli.coverage_cmd._emit")
@patch("evidara_cli.coverage_cmd.request_status", return_value=200)
@patch("evidara_cli.coverage_cmd.request_json", return_value=TEMPLATES)
@patch("evidara_cli.coverage_cmd.legal_search_base_url", return_value="http://ls.test")
@patch("evidara_cli.coverage_cmd.platform_control_base_url", return_value="http://pc.test")
def test_preflight_refuses_a_scaffold_before_anything_is_created(
    _pc: object, _ls: object, _req: object, _status: object, emit_mock: Any
) -> None:
    with pytest.raises(typer.Exit) as exc:
        coverage_preflight(
            overlay="at",
            template="ris_ogd_bundesrecht",
            check_search=True,
            human=False,
            correlation_id=None,
        )
    assert exc.value.exit_code == 1
    payload = _payload(emit_mock)
    assert payload["ok"] is False
    assert payload["decision"]["recommended_action"] == "engineering"
    assert payload["side_effect_level"] == "none"


@patch("evidara_cli.coverage_cmd._emit")
@patch("evidara_cli.coverage_cmd.request_status", return_value=200)
@patch("evidara_cli.coverage_cmd.request_json", return_value=TEMPLATES)
@patch("evidara_cli.coverage_cmd.platform_control_base_url", return_value="http://pc.test")
def test_preflight_reports_an_unknown_template(
    _pc: object, _req: object, _status: object, emit_mock: Any
) -> None:
    with pytest.raises(typer.Exit):
        coverage_preflight(
            overlay="ch",
            template="does_not_exist",
            check_search=False,
            human=False,
            correlation_id=None,
        )
    payload = _payload(emit_mock)
    assert payload["ok"] is False
    assert payload["status"] == "failed_terminal"


# --- watch --------------------------------------------------------------------------

_HEALTH_OK = {
    "overall_status": "ok",
    "processing_status_event_count": 2,
    "document_lifecycle_event_count": 2,
    "stages": [
        {"stage": "acquisition", "status": "ok", "detail": ""},
        {"stage": "document_intelligence", "status": "ok", "detail": ""},
        {"stage": "projection", "status": "ok", "detail": ""},
        {"stage": "search", "status": "ok", "detail": ""},
    ],
}


@patch("evidara_cli.coverage_cmd._emit")
@patch("evidara_cli.coverage_cmd._sleep")
@patch("evidara_cli.coverage_cmd.request_json")
@patch("evidara_cli.coverage_cmd.platform_control_base_url", return_value="http://pc.test")
def test_watch_polls_until_terminal(
    _pc: object, req_mock: Any, sleep_mock: Any, emit_mock: Any
) -> None:
    req_mock.side_effect = [
        {"run_id": "run_1", "status": "running", "refused": False},
        _HEALTH_OK,
        {"run_id": "run_1", "status": "completed", "refused": False},
        _HEALTH_OK,
    ]
    coverage_watch(
        run_id="run_1",
        until="run",
        timeout=60.0,
        interval=0.0,
        human=False,
        correlation_id=None,
    )
    payload = _payload(emit_mock)
    assert payload["ok"] is True
    assert payload["run_id"] == "run_1"
    assert payload["artifacts"]["polls"] == 2
    assert "stall_diagnosis" not in payload["artifacts"]
    assert sleep_mock.call_count == 1


@patch("evidara_cli.coverage_cmd._emit")
@patch("evidara_cli.coverage_cmd._sleep")
@patch("evidara_cli.coverage_cmd.request_json")
@patch("evidara_cli.coverage_cmd.platform_control_base_url", return_value="http://pc.test")
def test_watch_stops_immediately_on_a_refused_run(
    _pc: object, req_mock: Any, sleep_mock: Any, emit_mock: Any
) -> None:
    """A lock refusal is a terminal FAILED run — polling it for ten minutes helps nobody."""
    req_mock.side_effect = [
        {
            "run_id": "run_1",
            "status": "failed",
            "refused": True,
            "failure_reason": "Config key closed",
        },
        {"overall_status": "failed", "stages": []},
    ]
    with pytest.raises(typer.Exit):
        coverage_watch(
            run_id="run_1",
            until="processed",
            timeout=600.0,
            interval=5.0,
            human=False,
            correlation_id=None,
        )
    payload = _payload(emit_mock)
    assert payload["artifacts"]["polls"] == 1
    assert payload["artifacts"]["stall_diagnosis"]["cause"] == STALL_RUN_REFUSED
    assert sleep_mock.call_count == 0
    # Cancelling a run the lock already refused is not a compensation.
    assert payload["compensation"]["available"] is False


@patch("evidara_cli.coverage_cmd._emit")
@patch("evidara_cli.coverage_cmd._sleep")
@patch("evidara_cli.coverage_cmd.request_json")
@patch("evidara_cli.coverage_cmd.platform_control_base_url", return_value="http://pc.test")
def test_watch_diagnoses_a_run_that_never_leaves_pending(
    _pc: object, req_mock: Any, _sleep: object, emit_mock: Any
) -> None:
    req_mock.side_effect = [
        {"run_id": "run_1", "status": "pending", "refused": False},
        {"overall_status": "pending", "stages": []},
    ]
    with pytest.raises(typer.Exit):
        coverage_watch(
            run_id="run_1",
            until="run",
            timeout=0.0,
            interval=0.0,
            human=False,
            correlation_id=None,
        )
    diagnosis = _payload(emit_mock)["artifacts"]["stall_diagnosis"]
    assert diagnosis["cause"] == STALL_NO_DISPATCH_WORKER


@patch("evidara_cli.coverage_cmd._emit")
@patch("evidara_cli.coverage_cmd._sleep")
@patch("evidara_cli.coverage_cmd.request_json")
@patch("evidara_cli.coverage_cmd.platform_control_base_url", return_value="http://pc.test")
def test_watch_until_processed_diagnoses_a_silent_publish_path(
    _pc: object, req_mock: Any, _sleep: object, emit_mock: Any
) -> None:
    req_mock.side_effect = [
        {"run_id": "run_1", "status": "completed", "refused": False},
        {
            "overall_status": "pending",
            "processing_status_event_count": 0,
            "document_lifecycle_event_count": 0,
            "stages": [
                {"stage": "acquisition", "status": "ok", "detail": ""},
                {"stage": "document_intelligence", "status": "pending", "detail": ""},
            ],
        },
    ]
    with pytest.raises(typer.Exit):
        coverage_watch(
            run_id="run_1",
            until="processed",
            timeout=0.0,
            interval=0.0,
            human=False,
            correlation_id=None,
        )
    diagnosis = _payload(emit_mock)["artifacts"]["stall_diagnosis"]
    assert diagnosis["cause"] == STALL_PUBLISH_PATH_DISABLED


def test_watch_rejects_an_unknown_until_target() -> None:
    with pytest.raises(typer.Exit) as exc:
        coverage_watch(
            run_id="run_1",
            until="forever",
            timeout=0.0,
            interval=0.0,
            human=False,
            correlation_id=None,
        )
    assert exc.value.exit_code == 2


# --- enable -------------------------------------------------------------------------
#
# The flip guard moved into platform-control (#854), so these tests drive the *client
# half*: what the PUT carries, and what the command does with a 409 refusal or a 200
# that reports `applied` / `needs_human` / `evidence_binding`. The refusals themselves
# are derived and tested in
# `platform-control/tests/unit/test_blueprint_enablement_guard.py`.

_ACCEPTANCE_RUN = {
    "run_id": "run_ok",
    "source_id": "src_1",
    "source_version_id": "sv_1",
    "mode": "acceptance",
    "status": "completed",
    "refused": False,
    "captured_resources_count": 3,
}


def _templates_with(**overrides: Any) -> dict[str, Any]:
    """TEMPLATES with the lexfind row patched — the template under test."""
    rows = [dict(row) for row in TEMPLATES["data"]]
    rows[1] = {**rows[1], **overrides}
    return {"data": rows}


# The ordinary target: provider already LIVE, config key never turned.
_LIVE_NEVER_TURNED = _templates_with(acquisition_readiness="live")
_LIVE_FLIPPED = _templates_with(
    acquisition_readiness="live", enabled=True, source="override", launchable=True
)

#: What the server sends on a flip it accepted, binding the run to the template exactly.
_PUT_OK = {
    "enabled": True,
    "source": "override",
    "applied": True,
    "needs_human": False,
    "needs_human_reasons": [],
    "evidence_run_id": "run_ok",
    "evidence_binding": "template",
    "acceptance_verdict": {"is_acceptance_evidence": True, "refusals": []},
}


def _refusal(*codes: str, write_attempted: bool = False, **extra: Any) -> HttpJsonError:
    """The 409 platform-control returns when its ADR-0030 guard refuses."""
    body = {
        "detail": f"Refused: {codes[0]}.",
        "overlay_id": "ch",
        "provider_template_id": "lexfind_zh_hundegesetz",
        "refusals": [{"code": code, "detail": f"detail for {code}"} for code in codes],
        "needs_human": True,
        "write_attempted": write_attempted,
        **extra,
    }
    return HttpJsonError("HTTP 409", status_code=409, body=json.dumps(body))


def _enable(**kwargs: Any) -> None:
    """coverage_enable with the defaults every call needs, so tests state only the delta."""
    args: dict[str, Any] = {
        "overlay": "ch",
        "template": "lexfind_zh_hundegesetz",
        "evidence_run_id": None,
        "note": None,
        "enabled": True,
        "reopen_operator_kill_switch": False,
        "acknowledge_provider_below_live": False,
        "human": False,
        "correlation_id": None,
    }
    args.update(kwargs)
    coverage_enable(**args)


def _codes(payload: dict[str, Any]) -> list[str]:
    return [r["code"] for r in payload["artifacts"]["refusals"]]


@patch("evidara_cli.coverage_cmd._emit")
@patch("evidara_cli.coverage_cmd.request_json")
@patch("evidara_cli.coverage_cmd.platform_control_base_url", return_value="http://pc.test")
def test_enable_sends_the_evidence_and_both_acknowledgements(
    _pc: object, req_mock: Any, emit_mock: Any
) -> None:
    """#854: the guard cannot be server-side unless the client actually sends its inputs.

    A PUT carrying only `{enabled, note}` is the payload the admin dialog sent, and it
    is what made the panel the soft path around ADR-0030.
    """
    req_mock.side_effect = [_LIVE_NEVER_TURNED, _ACCEPTANCE_RUN, _PUT_OK, _LIVE_FLIPPED]
    _enable(
        evidence_run_id="run_ok",
        note="Evidence bundle under docs/runbooks/evidence/",
        reopen_operator_kill_switch=True,
        acknowledge_provider_below_live=True,
    )
    put_call = req_mock.call_args_list[2]
    assert put_call.args[0] == "PUT"
    body = put_call.kwargs["json_body"]
    assert body["evidence_run_id"] == "run_ok"
    assert body["reopen_operator_kill_switch"] is True
    assert body["acknowledge_provider_below_live"] is True
    # The audit note must carry the citation, not just the operator's prose.
    assert "run_ok" in body["note"]


@patch("evidara_cli.coverage_cmd._emit")
@patch("evidara_cli.coverage_cmd.request_json")
@patch("evidara_cli.coverage_cmd.platform_control_base_url", return_value="http://pc.test")
def test_enable_flips_the_key_and_proves_it_by_reading_it_back(
    _pc: object, req_mock: Any, emit_mock: Any
) -> None:
    req_mock.side_effect = [_LIVE_NEVER_TURNED, _ACCEPTANCE_RUN, _PUT_OK, _LIVE_FLIPPED]
    _enable(evidence_run_id="run_ok", note="Evidence bundle under docs/runbooks/evidence/")
    payload = _payload(emit_mock)
    assert payload["ok"] is True
    assert payload["side_effect_level"] == "reversible"
    verification = payload["artifacts"]["verification"]
    assert verification["applied"] is True
    assert verification["provenance"] == "override"
    # An exact template binding is a pass — that is what #846 asked for.
    binding = [e for e in payload["evidence"] if e["target"] == "adr-0030:acceptance-evidence"]
    assert binding and binding[0]["passed"] is True
    assert payload["artifacts"]["evidence_binding"] == "template"
    assert payload["status"] == "passed"


@patch("evidara_cli.coverage_cmd._emit")
@patch("evidara_cli.coverage_cmd.request_json")
@patch("evidara_cli.coverage_cmd.platform_control_base_url", return_value="http://pc.test")
def test_a_binding_weaker_than_template_exact_does_not_pass(
    _pc: object, req_mock: Any, emit_mock: Any
) -> None:
    """#846: a run that only matches by spec equality is confirmed by a human, not waved."""
    req_mock.side_effect = [
        _LIVE_NEVER_TURNED,
        _ACCEPTANCE_RUN,
        {
            **_PUT_OK,
            "evidence_binding": "acquisition_spec",
            "needs_human": True,
            "needs_human_reasons": ["binds by acquisition-spec equality"],
        },
        _LIVE_FLIPPED,
    ]
    _enable(evidence_run_id="run_ok", note="bundle")
    payload = _payload(emit_mock)
    assert payload["ok"] is True
    binding = [e for e in payload["evidence"] if e["target"] == "adr-0030:acceptance-evidence"]
    assert binding and binding[0]["passed"] is False
    judgement = [e for e in payload["evidence"] if e["target"] == "adr-0030:operator-judgement"]
    assert judgement and judgement[0]["passed"] is False
    assert payload["status"] == "needs_human"
    assert payload["decision"]["recommended_action"] == "needs-human"


@patch("evidara_cli.coverage_cmd._emit")
@patch("evidara_cli.coverage_cmd.request_json")
@patch("evidara_cli.coverage_cmd.platform_control_base_url", return_value="http://pc.test")
def test_enable_reports_a_server_refusal_verbatim_and_writes_nothing(
    _pc: object, req_mock: Any, emit_mock: Any
) -> None:
    """The refusal codes are a public interface: the envelope must not restate them."""
    req_mock.side_effect = [
        _LIVE_NEVER_TURNED,
        _ACCEPTANCE_RUN,
        _refusal(
            "evidence_run_is_not_acceptance_evidence",
            acceptance_verdict={
                "is_acceptance_evidence": False,
                "refusals": [{"code": "execution_mode_shadow", "detail": "SHADOW replays"}],
            },
        ),
    ]
    with pytest.raises(typer.Exit) as exc:
        _enable(evidence_run_id="run_ok", note="looked green")
    assert exc.value.exit_code == 1
    payload = _payload(emit_mock)
    assert payload["ok"] is False
    assert payload["side_effect_level"] == "none"
    assert _codes(payload) == ["evidence_run_is_not_acceptance_evidence"]
    verdict = payload["artifacts"]["refusal_response"]["acceptance_verdict"]
    assert [r["code"] for r in verdict["refusals"]] == ["execution_mode_shadow"]
    assert "Nothing was written" in payload["decision"]["reason"]
    assert req_mock.call_count == 3  # templates, run, PUT — no read-back


@patch("evidara_cli.coverage_cmd._emit")
@patch("evidara_cli.coverage_cmd.request_json")
@patch("evidara_cli.coverage_cmd.platform_control_base_url", return_value="http://pc.test")
def test_a_refusal_after_the_write_does_not_claim_nothing_happened(
    _pc: object, req_mock: Any, emit_mock: Any
) -> None:
    """The server's read-back failed *after* writing the override row (#631, #713)."""
    req_mock.side_effect = [
        _LIVE_NEVER_TURNED,
        _ACCEPTANCE_RUN,
        _refusal("read_back_disagrees", write_attempted=True),
    ]
    with pytest.raises(typer.Exit):
        _enable(evidence_run_id="run_ok", note="bundle")
    payload = _payload(emit_mock)
    assert payload["side_effect_level"] == "reversible"
    assert "The write was attempted" in payload["decision"]["reason"]


@patch("evidara_cli.coverage_cmd._emit")
@patch("evidara_cli.coverage_cmd.request_json")
@patch("evidara_cli.coverage_cmd.platform_control_base_url", return_value="http://pc.test")
def test_enable_refuses_when_the_client_disagrees_with_the_server(
    _pc: object, req_mock: Any, emit_mock: Any
) -> None:
    """The one refusal still derived here — the server cannot check itself against itself."""
    req_mock.side_effect = [_templates_with(acquisition_readiness="live", launchable=True)]
    with pytest.raises(typer.Exit):
        _enable(evidence_run_id="run_ok", note="bundle")
    assert _codes(_payload(emit_mock)) == ["classification_disagrees_with_server"]
    assert req_mock.call_count == 1  # no run fetch, no PUT


@patch("evidara_cli.coverage_cmd._emit")
@patch("evidara_cli.coverage_cmd.request_json")
@patch("evidara_cli.coverage_cmd.platform_control_base_url", return_value="http://pc.test")
def test_enable_fails_when_the_read_back_does_not_confirm_the_flip(
    _pc: object, req_mock: Any, emit_mock: Any
) -> None:
    """A 200 with `applied: true` is still corroborated against the inventory."""
    req_mock.side_effect = [
        _LIVE_NEVER_TURNED,
        _ACCEPTANCE_RUN,
        _PUT_OK,
        _LIVE_NEVER_TURNED,  # read-back: still disabled, still the shipped default
    ]
    with pytest.raises(typer.Exit) as exc:
        _enable(evidence_run_id="run_ok", note="bundle")
    assert exc.value.exit_code == 1
    payload = _payload(emit_mock)
    assert payload["ok"] is False
    assert payload["status"] == "failed_terminal"
    assert payload["artifacts"]["verification"]["applied"] is False
    assert "not report this key as flipped" in payload["decision"]["reason"]


@patch("evidara_cli.coverage_cmd._emit")
@patch("evidara_cli.coverage_cmd.request_json")
@patch("evidara_cli.coverage_cmd.platform_control_base_url", return_value="http://pc.test")
def test_enable_is_a_no_op_only_when_the_override_is_already_recorded(
    _pc: object, req_mock: Any, emit_mock: Any
) -> None:
    req_mock.return_value = _templates_with(
        acquisition_readiness="live", enabled=True, source="override", launchable=True
    )
    _enable()
    payload = _payload(emit_mock)
    assert payload["ok"] is True
    assert payload["artifacts"]["already_in_desired_state"] is True
    assert payload["side_effect_level"] == "none"
    assert req_mock.call_count == 1


@patch("evidara_cli.coverage_cmd._emit")
@patch("evidara_cli.coverage_cmd.request_json")
@patch("evidara_cli.coverage_cmd.platform_control_base_url", return_value="http://pc.test")
def test_enable_writes_the_audit_row_when_the_key_is_open_only_by_default(
    _pc: object, req_mock: Any, emit_mock: Any
) -> None:
    """Effective-true-by-default is not the desired state: ADR-0030 §5 wants the
    evidence citation recorded, which only the override row carries."""
    req_mock.side_effect = [
        _templates_with(
            acquisition_readiness="live", enabled=True, source="default", launchable=True
        ),
        _ACCEPTANCE_RUN,
        _PUT_OK,
        _LIVE_FLIPPED,
    ]
    _enable(evidence_run_id="run_ok", note="bundle")
    payload = _payload(emit_mock)
    assert payload["ok"] is True
    assert "already_in_desired_state" not in payload["artifacts"]
    assert req_mock.call_args_list[2].args[0] == "PUT"


@patch("evidara_cli.coverage_cmd._emit")
@patch("evidara_cli.coverage_cmd.request_json")
@patch("evidara_cli.coverage_cmd.platform_control_base_url", return_value="http://pc.test")
def test_disable_installs_a_kill_switch_on_a_key_that_was_only_never_turned(
    _pc: object, req_mock: Any, emit_mock: Any
) -> None:
    """#768: `never_turned` is waived by acceptance mode, an operator's `false` is not.
    Short-circuiting on the boolean alone left live traffic flowing at a portal the
    operator believed they had shut off, and exited 0."""
    req_mock.side_effect = [
        TEMPLATES,  # lexfind row: enabled False, source "default" => never_turned
        {"enabled": False, "source": "override", "applied": True, "needs_human": False},
        _templates_with(enabled=False, source="override"),
    ]
    _enable(enabled=False, note="Portal owner asked us to stop.")
    payload = _payload(emit_mock)
    assert payload["ok"] is True
    assert "already_in_desired_state" not in payload["artifacts"]
    put_call = req_mock.call_args_list[1]
    assert put_call.args[0] == "PUT"
    assert put_call.kwargs["json_body"] == {
        "enabled": False,
        "note": "Portal owner asked us to stop.",
        "evidence_run_id": None,
        "reopen_operator_kill_switch": False,
        "acknowledge_provider_below_live": False,
    }
    assert payload["artifacts"]["verification"]["applied"] is True
    assert payload["artifacts"]["template_after"]["config_key"] == "closed_by_operator"
    assert payload["artifacts"]["template_after"]["dispatchable_modes"] == []
    # Disabling needs no evidence, so nothing here is left for a human to confirm.
    assert payload["status"] == "passed"


def test_disable_requires_a_reason() -> None:
    with pytest.raises(typer.Exit) as exc:
        _enable(enabled=False)
    assert exc.value.exit_code == 2


# --- CLI surface (flag spellings and real exit codes) --------------------------------


@patch("evidara_cli.coverage_cmd.request_json")
@patch("evidara_cli.coverage_cmd.platform_control_base_url", return_value="http://pc.test")
def test_every_enable_flag_parses_through_the_real_cli(_pc: object, req_mock: Any) -> None:
    """The tests above call the function directly, so nothing else pins the flag
    spellings or the real process exit codes. A misspelled option would exit 2 here."""
    req_mock.side_effect = [_LIVE_NEVER_TURNED, _ACCEPTANCE_RUN, _PUT_OK, _LIVE_FLIPPED]
    result = CliRunner().invoke(
        app,
        [
            "workflow",
            "coverage",
            "enable",
            "--overlay",
            "ch",
            "--template",
            "lexfind_zh_hundegesetz",
            "--evidence-run-id",
            "run_ok",
            "--note",
            "why",
            "--enable",
            "--reopen-operator-kill-switch",
            "--acknowledge-provider-below-live",
            "--correlation-id",
            "cid-1",
        ],
    )
    # Exit 0 = every flag parsed and the flip completed. Exit 2 = a flag did not parse.
    assert result.exit_code == 0, result.output
    payload = json.loads(result.output)
    assert payload["inputs"]["acknowledge_provider_below_live"] is True
    assert payload["inputs"]["reopen_operator_kill_switch"] is True
    assert payload["artifacts"]["verification"]["applied"] is True


@patch("evidara_cli.coverage_cmd.request_json")
@patch("evidara_cli.coverage_cmd.platform_control_base_url", return_value="http://pc.test")
def test_enable_exit_codes_through_the_real_cli(_pc: object, req_mock: Any) -> None:
    req_mock.side_effect = [_LIVE_NEVER_TURNED, _refusal("no_evidence_run_cited")]
    runner = CliRunner()
    base = [
        "workflow",
        "coverage",
        "enable",
        "--overlay",
        "ch",
        "--template",
        "lexfind_zh_hundegesetz",
    ]

    refused = runner.invoke(app, base)
    assert refused.exit_code == 1
    assert json.loads(refused.output)["artifacts"]["refusals"][0]["code"] == (
        "no_evidence_run_cited"
    )

    missing_note = runner.invoke(app, [*base, "--disable"])
    assert missing_note.exit_code == 2


# ---------------------------------------------------------------------------------
# The gate ledger reaches the flip (#744)
# ---------------------------------------------------------------------------------


def _bundle_file(tmp_path: Any, *entries: tuple[str, str, str]) -> str:
    path = tmp_path / "summary.json"
    path.write_text(
        json.dumps(
            {
                "verdict": "pass",
                "checks": {
                    "captured_count": 3,
                    "gate_coverage": [
                        {"gate": gate, "outcome": outcome, "reason": reason}
                        for gate, outcome, reason in entries
                    ],
                    "skipped_gates": [gate for gate, _o, _r in entries],
                },
            }
        ),
        encoding="utf-8",
    )
    return str(path)


@patch("evidara_cli.coverage_cmd._emit")
@patch("evidara_cli.coverage_cmd.request_json")
@patch("evidara_cli.coverage_cmd.platform_control_base_url", return_value="http://pc.test")
def test_enable_refuses_a_bundle_whose_gate_could_not_run(
    _pc: object, req_mock: Any, emit_mock: Any, tmp_path: Any
) -> None:
    """A gate that was asked for and could not run is a hole, not a pass.

    Everything else about this run is good — completed, `mode=acceptance`, live
    execution mode, the right provider. Only the ledger disqualifies it, and the
    refusal has to name which gate.

    This is the one guard that did NOT move server-side in #854, and it is not an
    oversight: the ledger lives in a local harness `summary.json` and platform-control
    stores no gate record, so the server has nothing to re-derive it from. Deleting the
    client-side check would make this test go red, which is the point (#744).
    """
    req_mock.side_effect = [_LIVE_NEVER_TURNED]

    with pytest.raises(typer.Exit) as exc:
        _enable(
            evidence_run_id="run_ok",
            evidence_bundle=_bundle_file(
                tmp_path, ("indexed_title_ok", "not_evaluated", "no_legal_search_url")
            ),
        )

    assert exc.value.exit_code == 1
    payload = _payload(emit_mock)
    assert _codes(payload) == ["gate_not_evaluated"]
    coverage = payload["artifacts"]["gate_coverage"]
    assert [e["gate"] for e in coverage["not_evaluated"]] == ["indexed_title_ok"]
    assert "indexed_title_ok" in payload["artifacts"]["refusals"][0]["detail"]
    # It refuses before the PUT is ever built: one read, no write.
    assert req_mock.call_count == 1


@patch("evidara_cli.coverage_cmd._emit")
@patch("evidara_cli.coverage_cmd.request_json")
@patch("evidara_cli.coverage_cmd.platform_control_base_url", return_value="http://pc.test")
def test_enable_accepts_a_bundle_whose_gates_were_only_excluded(
    _pc: object, req_mock: Any, emit_mock: Any, tmp_path: Any
) -> None:
    """The other half of the split: a deselected gate must not block the flip.

    Without this, the escalation would be indistinguishable from refusing every run
    that ever skipped a gate — which is the old behaviour with extra steps.
    """
    req_mock.side_effect = [_LIVE_NEVER_TURNED, _ACCEPTANCE_RUN, _PUT_OK, _LIVE_FLIPPED]

    _enable(
        evidence_run_id="run_ok",
        note="Evidence bundle under docs/runbooks/evidence/",
        evidence_bundle=_bundle_file(
            tmp_path, ("title_ok", "excluded", "no_expected_title_declared")
        ),
    )

    payload = _payload(emit_mock)
    assert payload["artifacts"]["gate_coverage"]["refusals"] == []
    assert payload["artifacts"]["gate_coverage"]["excluded"][0]["gate"] == "title_ok"
    assert payload["artifacts"]["verification"]["applied"] is True


@patch("evidara_cli.coverage_cmd._emit")
@patch("evidara_cli.coverage_cmd.request_json")
@patch("evidara_cli.coverage_cmd.platform_control_base_url", return_value="http://pc.test")
def test_enable_stops_on_an_unreadable_bundle_rather_than_ignoring_it(
    _pc: object, req_mock: Any, _emit_mock: Any, tmp_path: Any
) -> None:
    """Degrading to "no gates skipped" would restore the defect the flag closes."""
    path = tmp_path / "summary.json"
    path.write_text("{not json", encoding="utf-8")

    with pytest.raises(typer.Exit) as exc:
        _enable(evidence_run_id="run_ok", evidence_bundle=str(path))

    assert exc.value.exit_code == 2
    assert req_mock.call_count == 0
