from __future__ import annotations

from unittest.mock import patch

import pytest
import typer

from evidara_cli.main import workflow_mvp_acceptance


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
            "metadata": [],
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
    assert payload["scenario_2"]["queries"][0]["query"] == "art 754"
    assert payload["scenario_3"]["document_id"] == "doc_123"
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
        {"totalResults": 13, "results": []},
        {"totalResults": 13, "results": []},
        {"totalResults": 13, "results": []},
        {"totalResults": 13, "results": []},
    ]

    with pytest.raises(typer.Exit) as exc_info:
        workflow_mvp_acceptance(human=False, correlation_id=None)

    assert exc_info.value.exit_code == 1
    emit_mock.assert_called_once()
    payload = emit_mock.call_args.args[0]
    assert payload["ok"] is False
    assert payload["scenario_3"]["document_id"] is None
    assert payload["scenario_3"]["document_http_code"] is None
