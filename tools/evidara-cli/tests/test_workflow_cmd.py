from __future__ import annotations

from unittest.mock import patch

import pytest
import typer

from evidara_cli.main import _detail_checks, workflow_mvp_acceptance
from evidara_cli.proposal import SourceSpecProposal
from evidara_cli.workflow_cmd import (
    run_evidence,
    run_status,
    search_inspect,
    search_verify,
    source_compensate,
    source_inspect,
    source_propose,
    source_verify,
)


@patch("evidara_cli.main._emit")
@patch("evidara_cli.main.request_status")
@patch("evidara_cli.main.request_json")
@patch("evidara_cli.main.platform_control_admin_base_url", return_value="http://admin.test")
@patch("evidara_cli.main.legal_search_frontend_base_url", return_value="http://ls-ui.test")
@patch("evidara_cli.main.legal_search_base_url", return_value="http://ls.test")
@patch("evidara_cli.main.platform_control_base_url", return_value="http://pc.test")
def test_workflow_mvp_acceptance_emits_summary(
    _pc_base: object,
    _ls_base: object,
    _ls_ui_base: object,
    _admin_base: object,
    request_json_mock: object,
    request_status_mock: object,
    emit_mock: object,
) -> None:
    request_status_mock.side_effect = [200, 200, 200, 200, 200, 200]
    request_json_mock.side_effect = [
        {"totalResults": 13, "results": [{"id": "doc_123"}]},
        {"totalResults": 13, "results": [{"id": "doc_456"}]},
        {"totalResults": 13, "results": [{"id": "doc_789"}]},
        {"totalResults": 13, "results": [{"id": "doc_101"}]},
        {
            "id": "doc_123",
            "title": "Example title",
            "subtitle": "Example subtitle",
            "metadataRows": [],
            "tabs": [],
        },
    ]

    workflow_mvp_acceptance(human=False, correlation_id=None)

    emit_mock.assert_called_once()
    payload = emit_mock.call_args.args[0]
    assert payload["ok"] is True
    assert payload["workflow"] == "mvp-acceptance"
    assert payload["evidence_pack_version"] == "tar-85-2026-04-11"
    assert payload["scenario_1"]["platform_control_health_http_code"] == 200
    assert payload["scenario_2"]["queries"][0]["query"] == "Bundesverfassung"
    assert payload["scenario_3"]["document_id"] == "doc_123"
    assert payload["scenario_3"]["checks"]["metadata_is_array"] is True
    assert payload["scenario_3"]["checks"]["subtitle_present"] is True
    assert payload["scenario_4"]["admin_ui_sources_http_code"] == 200


@patch("evidara_cli.main._emit")
@patch("evidara_cli.main.request_status")
@patch("evidara_cli.main.request_json")
@patch("evidara_cli.main.platform_control_admin_base_url", return_value="http://admin.test")
@patch("evidara_cli.main.legal_search_frontend_base_url", return_value="http://ls-ui.test")
@patch("evidara_cli.main.legal_search_base_url", return_value="http://ls.test")
@patch("evidara_cli.main.platform_control_base_url", return_value="http://pc.test")
def test_workflow_mvp_acceptance_exits_when_detail_cannot_be_resolved(
    _pc_base: object,
    _ls_base: object,
    _ls_ui_base: object,
    _admin_base: object,
    request_json_mock: object,
    request_status_mock: object,
    emit_mock: object,
) -> None:
    request_status_mock.side_effect = [200, 200, 200, 200, 200, 200]
    request_json_mock.side_effect = [
        {"totalResults": 0, "results": []},
        {"totalResults": 0, "results": []},
        {"totalResults": 0, "results": []},
        {"totalResults": 0, "results": []},
    ]

    with pytest.raises(typer.Exit) as exc_info:
        workflow_mvp_acceptance(human=False, correlation_id=None)

    assert exc_info.value.exit_code == 1
    emit_mock.assert_called_once()
    payload = emit_mock.call_args.args[0]
    assert payload["ok"] is False
    assert payload["scenario_2"]["queries"][0]["total_results"] == 0
    assert payload["scenario_3"]["document_id"] is None
    assert payload["scenario_3"]["document_http_code"] is None


def test_detail_checks_accepts_metadata_rows_shape():
    payload = {
        "id": "doc_123",
        "title": "Example title",
        "subtitle": "Example subtitle",
        "metadataRows": [],
        "tabs": [],
    }

    checks = _detail_checks(payload, document_id="doc_123")

    assert checks["metadata_is_array"] is True


def test_detail_checks_accepts_legacy_metadata_shape():
    payload = {
        "id": "doc_123",
        "title": "Example title",
        "subtitle": "Example subtitle",
        "metadata": [],
        "tabs": [],
    }

    checks = _detail_checks(payload, document_id="doc_123")

    assert checks["metadata_is_array"] is True


# ---------------------------------------------------------------------------
# proposal module
# ---------------------------------------------------------------------------


def test_source_spec_proposal_rule_based():
    p = SourceSpecProposal()
    result = p.propose("https://www.ris.bka.gv.at/laws")
    assert result["backend"] == "rule-based"
    assert "spec" in result
    assert "confidence" in result
    assert result["spec"]["seed_url"] == "https://www.ris.bka.gv.at/laws"
    assert result["spec"]["hostname"] == "www.ris.bka.gv.at"


def test_source_spec_proposal_detects_high_duplicate():
    p = SourceSpecProposal()
    result = p.propose("https://ris.bka.gv.at/", existing_source_names=["Ris"])
    assert result["duplicate_risk"] == "high"


def test_source_spec_proposal_no_duplicate():
    p = SourceSpecProposal()
    result = p.propose("https://novel-source.example.com/", existing_source_names=["OtherSource"])
    assert result["duplicate_risk"] in ("none", "low")


# ---------------------------------------------------------------------------
# workflow source inspect
# ---------------------------------------------------------------------------


@patch("evidara_cli.workflow_cmd._emit_envelope")
@patch("evidara_cli.workflow_cmd.request_json")
@patch("evidara_cli.workflow_cmd.request_status", return_value=200)
@patch("evidara_cli.workflow_cmd.platform_control_base_url", return_value="http://pc.test")
def test_source_inspect_no_source_id(
    _pc_base,
    _req_status,
    req_json_mock,
    emit_mock,
):
    req_json_mock.return_value = [{"display_name": "Ris"}, {"display_name": "BGbl"}]
    source_inspect(source_id=None, human=False, correlation_id=None)
    emit_mock.assert_called_once()
    payload = emit_mock.call_args.args[0]
    assert payload["ok"] is True
    assert payload["step"] == "source.inspect"
    assert payload["side_effect_level"] == "none"
    assert payload["artifacts"]["source_count"] == 2


@patch("evidara_cli.workflow_cmd._emit_envelope")
@patch("evidara_cli.workflow_cmd.request_json")
@patch("evidara_cli.workflow_cmd.request_status", return_value=200)
@patch("evidara_cli.workflow_cmd.platform_control_base_url", return_value="http://pc.test")
def test_source_inspect_with_source_id(
    _pc_base,
    _req_status,
    req_json_mock,
    emit_mock,
):
    req_json_mock.return_value = {
        "source_id": "src_abc",
        "display_name": "Test",
        "status": "active",
    }
    source_inspect(source_id="src_abc", human=False, correlation_id=None)
    payload = emit_mock.call_args.args[0]
    assert payload["ok"] is True
    assert payload["artifacts"]["source"]["source_id"] == "src_abc"


# ---------------------------------------------------------------------------
# workflow source propose
# ---------------------------------------------------------------------------


@patch("evidara_cli.workflow_cmd._emit_envelope")
@patch("evidara_cli.workflow_cmd.request_json")
@patch("evidara_cli.workflow_cmd.platform_control_base_url", return_value="http://pc.test")
def test_source_propose_no_duplicate(
    _pc_base,
    req_json_mock,
    emit_mock,
):
    req_json_mock.return_value = [{"display_name": "Existing"}]
    source_propose(seed_url="https://newsite.example.com/", human=False, correlation_id=None)
    payload = emit_mock.call_args.args[0]
    assert payload["ok"] is True
    assert payload["step"] == "source.propose"
    assert payload["side_effect_level"] == "none"
    assert "proposal" in payload["artifacts"]
    assert payload["artifacts"]["proposal"]["backend"] == "rule-based"


# ---------------------------------------------------------------------------
# workflow source verify
# ---------------------------------------------------------------------------


@patch("evidara_cli.workflow_cmd._emit_envelope")
@patch("evidara_cli.workflow_cmd.request_json")
@patch("evidara_cli.workflow_cmd.platform_control_base_url", return_value="http://pc.test")
def test_source_verify_by_source_id(
    _pc_base,
    req_json_mock,
    emit_mock,
):
    req_json_mock.return_value = {"source_id": "src_xyz", "status": "active"}
    source_verify(source_id="src_xyz", run_id=None, human=False, correlation_id=None)
    payload = emit_mock.call_args.args[0]
    assert payload["ok"] is True
    assert payload["step"] == "source.verify"
    assert payload["artifacts"]["source"]["status"] == "active"


def test_source_verify_requires_args():
    with pytest.raises(typer.Exit) as exc_info:
        source_verify(source_id=None, run_id=None, human=False, correlation_id=None)
    assert exc_info.value.exit_code == 2


# ---------------------------------------------------------------------------
# workflow source compensate
# ---------------------------------------------------------------------------


@patch("evidara_cli.workflow_cmd._emit_envelope")
@patch("evidara_cli.workflow_cmd.request_json")
@patch("evidara_cli.workflow_cmd.platform_control_base_url", return_value="http://pc.test")
def test_source_compensate_cancels_run(
    _pc_base,
    req_json_mock,
    emit_mock,
):
    req_json_mock.return_value = {"run_id": "run_001", "status": "cancelled"}
    source_compensate(
        source_id=None,
        run_id="run_001",
        reason="Test compensation",
        human=False,
        correlation_id=None,
    )
    payload = emit_mock.call_args.args[0]
    assert payload["ok"] is True
    assert payload["step"] == "source.compensate"
    assert payload["status"] == "compensated"
    assert payload["side_effect_level"] == "reversible"


def test_source_compensate_requires_args():
    with pytest.raises(typer.Exit) as exc_info:
        source_compensate(
            source_id=None,
            run_id=None,
            reason="test",
            human=False,
            correlation_id=None,
        )
    assert exc_info.value.exit_code == 2


# ---------------------------------------------------------------------------
# workflow search inspect
# ---------------------------------------------------------------------------


@patch("evidara_cli.workflow_cmd._emit_envelope")
@patch("evidara_cli.workflow_cmd.request_status", return_value=200)
@patch("evidara_cli.workflow_cmd.legal_search_base_url", return_value="http://ls.test")
def test_search_inspect_ok(_ls_base, _req_status, emit_mock):
    search_inspect(human=False, correlation_id=None)
    payload = emit_mock.call_args.args[0]
    assert payload["ok"] is True
    assert payload["step"] == "search.inspect"
    assert payload["side_effect_level"] == "none"


@patch("evidara_cli.workflow_cmd._emit_envelope")
@patch("evidara_cli.workflow_cmd.request_status", return_value=503)
@patch("evidara_cli.workflow_cmd.legal_search_base_url", return_value="http://ls.test")
def test_search_inspect_unreachable(_ls_base, _req_status, emit_mock):
    with pytest.raises(typer.Exit) as exc_info:
        search_inspect(human=False, correlation_id=None)
    assert exc_info.value.exit_code == 1
    payload = emit_mock.call_args.args[0]
    assert payload["ok"] is False


# ---------------------------------------------------------------------------
# workflow search verify
# ---------------------------------------------------------------------------


@patch("evidara_cli.workflow_cmd._emit_envelope")
@patch("evidara_cli.workflow_cmd.request_json")
@patch("evidara_cli.workflow_cmd.legal_search_base_url", return_value="http://ls.test")
def test_search_verify_passes(_ls_base, req_json_mock, emit_mock):
    req_json_mock.return_value = {"totalResults": 5, "results": []}
    search_verify(queries=["Bundesverfassung"], min_results=1, human=False, correlation_id=None)
    payload = emit_mock.call_args.args[0]
    assert payload["ok"] is True
    assert payload["step"] == "search.verify"
    assert payload["artifacts"]["query_results"][0]["total_results"] == 5


@patch("evidara_cli.workflow_cmd._emit_envelope")
@patch("evidara_cli.workflow_cmd.request_json")
@patch("evidara_cli.workflow_cmd.legal_search_base_url", return_value="http://ls.test")
def test_search_verify_fails_when_below_min(_ls_base, req_json_mock, emit_mock):
    req_json_mock.return_value = {"totalResults": 0, "results": []}
    with pytest.raises(typer.Exit) as exc_info:
        search_verify(queries=["obscure"], min_results=1, human=False, correlation_id=None)
    assert exc_info.value.exit_code == 1
    payload = emit_mock.call_args.args[0]
    assert payload["ok"] is False


# ---------------------------------------------------------------------------
# workflow run status
# ---------------------------------------------------------------------------


@patch("evidara_cli.workflow_cmd._emit_envelope")
@patch("evidara_cli.workflow_cmd.request_json")
@patch("evidara_cli.workflow_cmd.platform_control_base_url", return_value="http://pc.test")
def test_run_status_emits_envelope(_pc_base, req_json_mock, emit_mock):
    req_json_mock.return_value = {"run_id": "run_abc", "status": "completed"}
    run_status(run_id="run_abc", human=False, correlation_id=None)
    payload = emit_mock.call_args.args[0]
    assert payload["ok"] is True
    assert payload["step"] == "run.status"
    assert payload["artifacts"]["run"]["status"] == "completed"
    assert payload["compensation"]["available"] is False  # completed run


# ---------------------------------------------------------------------------
# workflow run evidence
# ---------------------------------------------------------------------------


@patch("evidara_cli.workflow_cmd._emit_envelope")
@patch("evidara_cli.workflow_cmd.request_json")
@patch("evidara_cli.workflow_cmd.platform_control_base_url", return_value="http://pc.test")
def test_run_evidence_collects_resources(_pc_base, req_json_mock, emit_mock):
    req_json_mock.side_effect = [
        {
            "run_id": "run_abc",
            "status": "completed",
            "mode": "acceptance",
            "refused": False,
            "source_id": "src_1",
            "source_version_id": "ver_1",
        },
        [{"resource_id": "r1"}, {"resource_id": "r2"}],
        {"overall_status": "ok", "stages": []},
        {"data": [{"source_version_id": "ver_1", "execution_mode": "live"}]},
    ]
    run_evidence(run_id="run_abc", human=False, correlation_id=None)
    payload = emit_mock.call_args.args[0]
    assert payload["ok"] is True
    assert payload["step"] == "run.evidence"
    assert payload["artifacts"]["captured_resource_count"] == 2
    assert payload["artifacts"]["acceptance_verdict"]["is_acceptance_evidence"] is True
    assert payload["decision"]["recommended_action"] == "flip-enablement"


@patch("evidara_cli.workflow_cmd._emit_envelope")
@patch("evidara_cli.workflow_cmd.request_json")
@patch("evidara_cli.workflow_cmd.platform_control_base_url", return_value="http://pc.test")
def test_run_evidence_refuses_a_shadow_run_as_acceptance_evidence(
    _pc_base, req_json_mock, emit_mock
):
    """ADR-0030 §2: SHADOW replays cassettes, so a green run proves nothing about the portal."""
    req_json_mock.side_effect = [
        {
            "run_id": "run_abc",
            "status": "completed",
            "mode": "acceptance",
            "refused": False,
            "source_id": "src_1",
            "source_version_id": "ver_1",
        },
        [{"resource_id": "r1"}],
        {"overall_status": "ok", "stages": []},
        {"data": [{"source_version_id": "ver_1", "execution_mode": "shadow"}]},
    ]
    run_evidence(run_id="run_abc", human=False, correlation_id=None)
    payload = emit_mock.call_args.args[0]
    verdict = payload["artifacts"]["acceptance_verdict"]
    assert verdict["is_acceptance_evidence"] is False
    assert [r["code"] for r in verdict["refusals"]] == ["execution_mode_shadow"]
    assert payload["decision"]["recommended_action"] == "verify"
