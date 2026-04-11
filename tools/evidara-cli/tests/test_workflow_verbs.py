from __future__ import annotations

from unittest.mock import patch

import pytest
import typer

from evidara_cli.workflow_cmd import (
    run_evidence,
    run_status,
    search_inspect,
    search_verify_document_detail,
    search_verify_query_pack,
    source_apply,
    source_compensate,
    source_inspect,
    source_propose,
    source_verify,
)

# ---------------------------------------------------------------------------
# source inspect
# ---------------------------------------------------------------------------


@patch("evidara_cli.workflow_cmd._emit")
@patch("evidara_cli.workflow_cmd.request_status")
@patch("evidara_cli.workflow_cmd.platform_control_base_url", return_value="http://pc.test")
def test_source_inspect_passes(
    _pc_base: object,
    request_status_mock: object,
    emit_mock: object,
) -> None:
    request_status_mock.side_effect = [200, 200]
    source_inspect(source_id=None, run_id="wf_test_001", human=False, correlation_id=None)

    emit_mock.assert_called_once()
    env = emit_mock.call_args.args[0]
    assert env["ok"] is True
    assert env["workflow"] == "source-draft"
    assert env["step"] == "source.inspect"
    assert env["status"] == "passed"
    assert env["side_effect_level"] == "none"
    assert "timestamp" in env


@patch("evidara_cli.workflow_cmd._emit")
@patch("evidara_cli.workflow_cmd.request_status")
@patch("evidara_cli.workflow_cmd.platform_control_base_url", return_value="http://pc.test")
def test_source_inspect_fails_when_health_not_200(
    _pc_base: object,
    request_status_mock: object,
    emit_mock: object,
) -> None:
    request_status_mock.side_effect = [503, 503]
    with pytest.raises(typer.Exit) as exc_info:
        source_inspect(source_id=None, run_id="wf_test_002", human=False, correlation_id=None)
    assert exc_info.value.exit_code == 1
    env = emit_mock.call_args.args[0]
    assert env["ok"] is False
    assert env["status"] == "failed_retriable"


# ---------------------------------------------------------------------------
# source propose
# ---------------------------------------------------------------------------


@patch("evidara_cli.workflow_cmd._emit")
def test_source_propose_passes(emit_mock: object) -> None:
    source_propose(
        seed_url="https://www.ris.bka.gv.at/",
        name="ris-source",
        run_id="wf_test_010",
        human=False,
        correlation_id=None,
    )
    emit_mock.assert_called_once()
    env = emit_mock.call_args.args[0]
    assert env["ok"] is True
    assert env["step"] == "source.propose"
    assert env["side_effect_level"] == "none"
    assert "spec" in env["artifacts"]
    assert env["artifacts"]["spec"]["name"] == "ris-source"
    assert env["artifacts"]["spec"]["dspy_assisted"] is False
    assert "apply" in env["next_actions"]


@patch("evidara_cli.workflow_cmd._emit")
def test_source_propose_name_derived_from_domain(emit_mock: object) -> None:
    source_propose(
        seed_url="https://example.at/docs",
        name=None,
        run_id="wf_test_011",
        human=False,
        correlation_id=None,
    )
    env = emit_mock.call_args.args[0]
    assert env["ok"] is True
    assert "example" in env["artifacts"]["spec"]["name"]


# ---------------------------------------------------------------------------
# source apply
# ---------------------------------------------------------------------------


@patch("evidara_cli.workflow_cmd._emit")
@patch("evidara_cli.workflow_cmd.request_json")
@patch("evidara_cli.workflow_cmd.platform_control_base_url", return_value="http://pc.test")
def test_source_apply_passes(
    _pc_base: object,
    request_json_mock: object,
    emit_mock: object,
) -> None:
    request_json_mock.return_value = {"wizard_project_id": "proj_abc", "name": "test-source"}
    source_apply(
        name="test-source",
        description=None,
        run_id="wf_test_020",
        human=False,
        correlation_id=None,
    )
    emit_mock.assert_called_once()
    env = emit_mock.call_args.args[0]
    assert env["ok"] is True
    assert env["step"] == "source.apply"
    assert env["status"] == "passed"
    assert env["side_effect_level"] == "reversible"
    assert env["artifacts"]["wizard_project_id"] == "proj_abc"
    assert env["compensation"]["available"] is True
    assert "verify" in env["next_actions"]


@patch("evidara_cli.workflow_cmd._emit")
@patch("evidara_cli.workflow_cmd.request_json")
@patch("evidara_cli.workflow_cmd.platform_control_base_url", return_value="http://pc.test")
def test_source_apply_fails_when_no_project_id(
    _pc_base: object,
    request_json_mock: object,
    emit_mock: object,
) -> None:
    request_json_mock.return_value = {"unexpected": "shape"}
    with pytest.raises(typer.Exit) as exc_info:
        source_apply(
            name="bad-response",
            description=None,
            run_id="wf_test_021",
            human=False,
            correlation_id=None,
        )
    assert exc_info.value.exit_code == 1
    env = emit_mock.call_args.args[0]
    assert env["ok"] is False


# ---------------------------------------------------------------------------
# source verify
# ---------------------------------------------------------------------------


@patch("evidara_cli.workflow_cmd._emit")
@patch("evidara_cli.workflow_cmd.request_json")
@patch("evidara_cli.workflow_cmd.platform_control_base_url", return_value="http://pc.test")
def test_source_verify_passes(
    _pc_base: object,
    request_json_mock: object,
    emit_mock: object,
) -> None:
    request_json_mock.return_value = {"wizard_project_id": "proj_abc", "name": "test-source"}
    source_verify(
        project_id="proj_abc",
        run_id="wf_test_030",
        human=False,
        correlation_id=None,
    )
    emit_mock.assert_called_once()
    env = emit_mock.call_args.args[0]
    assert env["ok"] is True
    assert env["step"] == "source.verify"
    assert env["status"] == "passed"
    assert env["compensation"]["available"] is True


@patch("evidara_cli.workflow_cmd._emit")
@patch("evidara_cli.workflow_cmd.request_json")
@patch("evidara_cli.workflow_cmd.platform_control_base_url", return_value="http://pc.test")
def test_source_verify_fails_when_name_missing(
    _pc_base: object,
    request_json_mock: object,
    emit_mock: object,
) -> None:
    request_json_mock.return_value = {"wizard_project_id": "proj_abc"}
    with pytest.raises(typer.Exit) as exc_info:
        source_verify(
            project_id="proj_abc",
            run_id="wf_test_031",
            human=False,
            correlation_id=None,
        )
    assert exc_info.value.exit_code == 1
    env = emit_mock.call_args.args[0]
    assert env["ok"] is False
    assert env["status"] == "failed_terminal"


# ---------------------------------------------------------------------------
# source compensate
# ---------------------------------------------------------------------------


@patch("evidara_cli.workflow_cmd._emit")
def test_source_compensate_always_succeeds(emit_mock: object) -> None:
    source_compensate(
        project_id="proj_abc",
        run_id="wf_test_040",
        reason="test-recovery",
        human=False,
        correlation_id=None,
    )
    emit_mock.assert_called_once()
    env = emit_mock.call_args.args[0]
    assert env["ok"] is True
    assert env["step"] == "source.compensate"
    assert env["status"] == "compensated"
    assert env["side_effect_level"] == "reversible"
    assert env["compensation"]["available"] is False


@patch("evidara_cli.workflow_cmd._emit")
def test_source_compensate_without_project_id(emit_mock: object) -> None:
    source_compensate(
        project_id=None,
        run_id="wf_test_041",
        reason="operator-requested",
        human=False,
        correlation_id=None,
    )
    env = emit_mock.call_args.args[0]
    assert env["ok"] is True
    assert env["status"] == "compensated"


# ---------------------------------------------------------------------------
# search inspect
# ---------------------------------------------------------------------------


@patch("evidara_cli.workflow_cmd._emit")
@patch("evidara_cli.workflow_cmd.request_status")
@patch("evidara_cli.workflow_cmd.legal_search_base_url", return_value="http://ls.test")
def test_search_inspect_passes(
    _ls_base: object,
    request_status_mock: object,
    emit_mock: object,
) -> None:
    request_status_mock.return_value = 200
    search_inspect(run_id="wf_test_050", human=False, correlation_id=None)
    env = emit_mock.call_args.args[0]
    assert env["ok"] is True
    assert env["step"] == "search.inspect"
    assert env["side_effect_level"] == "none"


@patch("evidara_cli.workflow_cmd._emit")
@patch("evidara_cli.workflow_cmd.request_status")
@patch("evidara_cli.workflow_cmd.legal_search_base_url", return_value="http://ls.test")
def test_search_inspect_fails_on_non_200(
    _ls_base: object,
    request_status_mock: object,
    emit_mock: object,
) -> None:
    request_status_mock.return_value = 503
    with pytest.raises(typer.Exit):
        search_inspect(run_id="wf_test_051", human=False, correlation_id=None)
    env = emit_mock.call_args.args[0]
    assert env["ok"] is False


# ---------------------------------------------------------------------------
# search verify-query-pack
# ---------------------------------------------------------------------------


@patch("evidara_cli.workflow_cmd._emit")
@patch("evidara_cli.workflow_cmd.request_json")
@patch("evidara_cli.workflow_cmd.legal_search_base_url", return_value="http://ls.test")
def test_search_verify_query_pack_passes(
    _ls_base: object,
    request_json_mock: object,
    emit_mock: object,
) -> None:
    request_json_mock.return_value = {"totalResults": 5, "results": []}
    search_verify_query_pack(
        queries="art 754,haftung",
        min_results=1,
        run_id="wf_test_060",
        human=False,
        correlation_id=None,
    )
    env = emit_mock.call_args.args[0]
    assert env["ok"] is True
    assert env["step"] == "search.verify-query-pack"
    assert len(env["artifacts"]["query_results"]) == 2
    assert all(r["meets_min"] for r in env["artifacts"]["query_results"])


@patch("evidara_cli.workflow_cmd._emit")
@patch("evidara_cli.workflow_cmd.request_json")
@patch("evidara_cli.workflow_cmd.legal_search_base_url", return_value="http://ls.test")
def test_search_verify_query_pack_fails_below_min(
    _ls_base: object,
    request_json_mock: object,
    emit_mock: object,
) -> None:
    request_json_mock.return_value = {"totalResults": 0, "results": []}
    with pytest.raises(typer.Exit):
        search_verify_query_pack(
            queries="obscure-query",
            min_results=5,
            run_id="wf_test_061",
            human=False,
            correlation_id=None,
        )
    env = emit_mock.call_args.args[0]
    assert env["ok"] is False


# ---------------------------------------------------------------------------
# search verify-document-detail
# ---------------------------------------------------------------------------


@patch("evidara_cli.workflow_cmd._emit")
@patch("evidara_cli.workflow_cmd.request_json")
@patch("evidara_cli.workflow_cmd.legal_search_base_url", return_value="http://ls.test")
def test_search_verify_document_detail_passes(
    _ls_base: object,
    request_json_mock: object,
    emit_mock: object,
) -> None:
    request_json_mock.return_value = {
        "id": "doc_001",
        "title": "Test Title",
        "subtitle": "Test Subtitle",
        "metadata": [],
        "tabs": [],
    }
    search_verify_document_detail(
        document_id="doc_001",
        run_id="wf_test_070",
        human=False,
        correlation_id=None,
    )
    env = emit_mock.call_args.args[0]
    assert env["ok"] is True
    assert env["step"] == "search.verify-document-detail"
    assert all(env["artifacts"]["checks"].values())


@patch("evidara_cli.workflow_cmd._emit")
@patch("evidara_cli.workflow_cmd.request_json")
@patch("evidara_cli.workflow_cmd.legal_search_base_url", return_value="http://ls.test")
def test_search_verify_document_detail_fails_on_id_mismatch(
    _ls_base: object,
    request_json_mock: object,
    emit_mock: object,
) -> None:
    request_json_mock.return_value = {
        "id": "doc_WRONG",
        "title": "Title",
        "subtitle": "Sub",
        "metadata": [],
        "tabs": [],
    }
    with pytest.raises(typer.Exit):
        search_verify_document_detail(
            document_id="doc_001",
            run_id="wf_test_071",
            human=False,
            correlation_id=None,
        )
    env = emit_mock.call_args.args[0]
    assert env["ok"] is False
    assert env["artifacts"]["checks"]["id_matches"] is False


# ---------------------------------------------------------------------------
# run evidence + run status
# ---------------------------------------------------------------------------


@patch("evidara_cli.workflow_cmd._emit")
def test_run_evidence_returns_summary(emit_mock: object) -> None:
    run_evidence(run_id="wf_unknown_999", human=False)
    emit_mock.assert_called_once()
    summary = emit_mock.call_args.args[0]
    assert summary["run_id"] == "wf_unknown_999"
    assert "note" in summary


@patch("evidara_cli.workflow_cmd._emit")
def test_run_status_returns_note(emit_mock: object) -> None:
    run_status(run_id="wf_unknown_999", human=False)
    emit_mock.assert_called_once()
    result = emit_mock.call_args.args[0]
    assert result["run_id"] == "wf_unknown_999"
    assert result["status"] == "unknown"
    assert "note" in result
