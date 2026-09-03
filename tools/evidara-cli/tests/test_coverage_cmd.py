from __future__ import annotations

from typing import Any
from unittest.mock import patch

import pytest
import typer

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

_ACCEPTANCE_RUN = {
    "run_id": "run_ok",
    "source_id": "src_1",
    "source_version_id": "sv_1",
    "mode": "acceptance",
    "status": "completed",
    "refused": False,
    "captured_resources_count": 3,
}
_VERSIONS_LIVE = {
    "data": [
        {
            "source_version_id": "sv_1",
            "execution_mode": "live",
            "acquisition_spec": {"provider": "lexfind"},
        }
    ]
}


def _templates_with(**overrides: Any) -> dict[str, Any]:
    """TEMPLATES with the lexfind row patched — the template under test."""
    rows = [dict(row) for row in TEMPLATES["data"]]
    rows[1] = {**rows[1], **overrides}
    return {"data": rows}


_AFTER_FLIPPED = _templates_with(enabled=True, source="override", updated_by="op_1")


@patch("evidara_cli.coverage_cmd._emit")
@patch("evidara_cli.coverage_cmd.request_json")
@patch("evidara_cli.coverage_cmd.platform_control_base_url", return_value="http://pc.test")
def test_enable_flips_the_key_and_proves_it_by_reading_it_back(
    _pc: object, req_mock: Any, emit_mock: Any
) -> None:
    req_mock.side_effect = [
        TEMPLATES,
        _ACCEPTANCE_RUN,
        _VERSIONS_LIVE,
        {"enabled": True, "source": "override"},
        _AFTER_FLIPPED,
    ]
    coverage_enable(
        overlay="ch",
        template="lexfind_zh_hundegesetz",
        evidence_run_id="run_ok",
        note="Evidence bundle under docs/runbooks/evidence/",
        enabled=True,
        reopen_operator_kill_switch=False,
        human=False,
        correlation_id=None,
    )
    payload = _payload(emit_mock)
    assert payload["ok"] is True
    assert payload["side_effect_level"] == "reversible"
    verification = payload["artifacts"]["verification"]
    assert verification["applied"] is True
    assert verification["provenance"] == "override"
    # The audit note must carry the citation, not just the operator's prose.
    put_call = req_mock.call_args_list[3]
    assert put_call.args[0] == "PUT"
    assert "run_ok" in put_call.kwargs["json_body"]["note"]
    # Flipping the config key does not open the code key, and the envelope says so.
    code_key = [e for e in payload["evidence"] if e["target"] == "adr-0030:code-key"]
    assert code_key and "not production" in code_key[0]["note"]


@patch("evidara_cli.coverage_cmd._emit")
@patch("evidara_cli.coverage_cmd.request_json")
@patch("evidara_cli.coverage_cmd.platform_control_base_url", return_value="http://pc.test")
def test_enable_refuses_a_shadow_run_and_writes_nothing(
    _pc: object, req_mock: Any, emit_mock: Any
) -> None:
    """The refusal ADR-0030 §2 names. A green SHADOW run must not reach the PUT."""
    req_mock.side_effect = [
        TEMPLATES,
        _ACCEPTANCE_RUN,
        {
            "data": [
                {
                    "source_version_id": "sv_1",
                    "execution_mode": "shadow",
                    "acquisition_spec": {"provider": "lexfind"},
                }
            ]
        },
    ]
    with pytest.raises(typer.Exit) as exc:
        coverage_enable(
            overlay="ch",
            template="lexfind_zh_hundegesetz",
            evidence_run_id="run_ok",
            note=None,
            enabled=True,
            reopen_operator_kill_switch=False,
            human=False,
            correlation_id=None,
        )
    assert exc.value.exit_code == 1
    payload = _payload(emit_mock)
    assert payload["ok"] is False
    assert payload["side_effect_level"] == "none"
    assert [r["code"] for r in payload["artifacts"]["refusals"]] == [
        "evidence_run_is_not_acceptance_evidence"
    ]
    verdict = payload["artifacts"]["acceptance_verdict"]
    assert [r["code"] for r in verdict["refusals"]] == ["execution_mode_shadow"]
    # Three reads, no write.
    assert req_mock.call_count == 3


@patch("evidara_cli.coverage_cmd._emit")
@patch("evidara_cli.coverage_cmd.request_json", return_value=TEMPLATES)
@patch("evidara_cli.coverage_cmd.platform_control_base_url", return_value="http://pc.test")
def test_enable_refuses_without_a_cited_run(_pc: object, req_mock: Any, emit_mock: Any) -> None:
    with pytest.raises(typer.Exit):
        coverage_enable(
            overlay="ch",
            template="lexfind_zh_hundegesetz",
            evidence_run_id=None,
            note="trust me",
            enabled=True,
            reopen_operator_kill_switch=False,
            human=False,
            correlation_id=None,
        )
    payload = _payload(emit_mock)
    assert [r["code"] for r in payload["artifacts"]["refusals"]] == ["no_evidence_run_cited"]
    assert req_mock.call_count == 1


@patch("evidara_cli.coverage_cmd._emit")
@patch("evidara_cli.coverage_cmd.request_json")
@patch("evidara_cli.coverage_cmd.platform_control_base_url", return_value="http://pc.test")
def test_enable_refuses_evidence_from_a_different_provider(
    _pc: object, req_mock: Any, emit_mock: Any
) -> None:
    req_mock.side_effect = [
        TEMPLATES,
        _ACCEPTANCE_RUN,
        {
            "data": [
                {
                    "source_version_id": "sv_1",
                    "execution_mode": "live",
                    "acquisition_spec": {"provider": "fedlex_sparql"},
                }
            ]
        },
    ]
    with pytest.raises(typer.Exit):
        coverage_enable(
            overlay="ch",
            template="lexfind_zh_hundegesetz",
            evidence_run_id="run_ok",
            note=None,
            enabled=True,
            reopen_operator_kill_switch=False,
            human=False,
            correlation_id=None,
        )
    payload = _payload(emit_mock)
    assert [r["code"] for r in payload["artifacts"]["refusals"]] == [
        "evidence_run_provider_mismatch"
    ]
    assert payload["artifacts"]["evidence_binding"] == "none"


@patch("evidara_cli.coverage_cmd._emit")
@patch("evidara_cli.coverage_cmd.request_json")
@patch("evidara_cli.coverage_cmd.platform_control_base_url", return_value="http://pc.test")
def test_enable_refuses_to_reopen_an_operator_kill_switch(
    _pc: object, req_mock: Any, emit_mock: Any
) -> None:
    """Acceptance evidence does not waive somebody's deliberate kill switch."""
    req_mock.side_effect = [
        _templates_with(enabled=False, source="override"),
        _ACCEPTANCE_RUN,
        _VERSIONS_LIVE,
    ]
    with pytest.raises(typer.Exit):
        coverage_enable(
            overlay="ch",
            template="lexfind_zh_hundegesetz",
            evidence_run_id="run_ok",
            note=None,
            enabled=True,
            reopen_operator_kill_switch=False,
            human=False,
            correlation_id=None,
        )
    payload = _payload(emit_mock)
    assert [r["code"] for r in payload["artifacts"]["refusals"]] == [
        "operator_kill_switch_not_acknowledged"
    ]
    assert req_mock.call_count == 3


@patch("evidara_cli.coverage_cmd._emit")
@patch("evidara_cli.coverage_cmd.request_json")
@patch("evidara_cli.coverage_cmd.platform_control_base_url", return_value="http://pc.test")
def test_enable_fails_when_the_read_back_does_not_confirm_the_flip(
    _pc: object, req_mock: Any, emit_mock: Any
) -> None:
    """A 200 is not proof. This is the #631 / #713 failure mode, caught."""
    req_mock.side_effect = [
        TEMPLATES,
        _ACCEPTANCE_RUN,
        _VERSIONS_LIVE,
        {"enabled": True, "source": "override"},
        TEMPLATES,  # read-back: still disabled, still the shipped default
    ]
    with pytest.raises(typer.Exit) as exc:
        coverage_enable(
            overlay="ch",
            template="lexfind_zh_hundegesetz",
            evidence_run_id="run_ok",
            note=None,
            enabled=True,
            reopen_operator_kill_switch=False,
            human=False,
            correlation_id=None,
        )
    assert exc.value.exit_code == 1
    payload = _payload(emit_mock)
    assert payload["ok"] is False
    assert payload["status"] == "failed_terminal"
    assert [p["code"] for p in payload["artifacts"]["verification"]["problems"]] == [
        "read_back_disagrees",
        "no_override_recorded",
    ]
    assert "not report this key as flipped" in payload["decision"]["reason"]


@patch("evidara_cli.coverage_cmd._emit")
@patch("evidara_cli.coverage_cmd.request_json", return_value=TEMPLATES)
@patch("evidara_cli.coverage_cmd.platform_control_base_url", return_value="http://pc.test")
def test_enable_is_a_no_op_when_the_key_is_already_open(
    _pc: object, req_mock: Any, emit_mock: Any
) -> None:
    coverage_enable(
        overlay="ch",
        template="fedlex_sparql_constitution_de",
        evidence_run_id=None,
        note=None,
        enabled=True,
        reopen_operator_kill_switch=False,
        human=False,
        correlation_id=None,
    )
    payload = _payload(emit_mock)
    assert payload["ok"] is True
    assert payload["artifacts"]["already_in_desired_state"] is True
    assert payload["side_effect_level"] == "none"
    assert req_mock.call_count == 1


@patch("evidara_cli.coverage_cmd._emit")
@patch("evidara_cli.coverage_cmd.request_json")
@patch("evidara_cli.coverage_cmd.platform_control_base_url", return_value="http://pc.test")
def test_disable_needs_no_evidence_but_does_need_a_reason(
    _pc: object, req_mock: Any, emit_mock: Any
) -> None:
    with pytest.raises(typer.Exit) as exc:
        coverage_enable(
            overlay="ch",
            template="fedlex_sparql_constitution_de",
            evidence_run_id=None,
            note=None,
            enabled=False,
            reopen_operator_kill_switch=False,
            human=False,
            correlation_id=None,
        )
    assert exc.value.exit_code == 2
    assert req_mock.call_count == 0

    req_mock.side_effect = [
        TEMPLATES,
        {"enabled": False, "source": "override"},
        {
            "data": [
                {**TEMPLATES["data"][0], "enabled": False, "source": "override"},
                *TEMPLATES["data"][1:],
            ]
        },
    ]
    coverage_enable(
        overlay="ch",
        template="fedlex_sparql_constitution_de",
        evidence_run_id=None,
        note="Portal rate-limited us; pausing until Monday.",
        enabled=False,
        reopen_operator_kill_switch=False,
        human=False,
        correlation_id=None,
    )
    payload = emit_mock.call_args.args[0]
    assert payload["ok"] is True
    assert payload["artifacts"]["verification"]["applied"] is True
