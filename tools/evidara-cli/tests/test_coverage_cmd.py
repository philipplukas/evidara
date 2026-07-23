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
from evidara_cli.coverage_cmd import coverage_preflight, coverage_templates, coverage_watch

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
