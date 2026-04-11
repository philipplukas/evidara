from __future__ import annotations

from evidara_cli.workflow_envelope import (
    build_envelope,
    compensation_command,
    evidence_check,
    evidence_http,
)


def test_build_envelope_minimal() -> None:
    env = build_envelope(
        ok=True,
        workflow="source-draft",
        run_id="wf_test_001",
        step="source.inspect",
        status="passed",
        side_effect_level="none",
    )
    assert env["ok"] is True
    assert env["workflow"] == "source-draft"
    assert env["run_id"] == "wf_test_001"
    assert env["step"] == "source.inspect"
    assert env["status"] == "passed"
    assert env["side_effect_level"] == "none"
    assert env["inputs"] == {}
    assert env["artifacts"] == {}
    assert env["evidence"] == []
    assert env["decision"] == {}
    assert env["next_actions"] == []
    assert env["compensation"] == {"available": False}
    assert "timestamp" in env


def test_build_envelope_full() -> None:
    env = build_envelope(
        ok=False,
        workflow="search-verify",
        run_id="wf_search_001",
        step="search.verify-query-pack",
        status="failed_retriable",
        side_effect_level="none",
        inputs={"queries": ["test"]},
        artifacts={"query_results": []},
        evidence=[{"kind": "http", "target": "legal-search:/v1/search", "status_code": 500}],
        decision={"recommended_action": "retry", "reason": "timeout"},
        next_actions=["retry", "inspect"],
        compensation={"available": False},
    )
    assert env["ok"] is False
    assert env["inputs"] == {"queries": ["test"]}
    assert len(env["evidence"]) == 1
    assert env["next_actions"] == ["retry", "inspect"]
    assert env["decision"]["recommended_action"] == "retry"


def test_build_envelope_compensation_not_none_when_provided() -> None:
    comp = {"available": True, "command": "evidara workflow source compensate --run-id wf_x"}
    env = build_envelope(
        ok=True,
        workflow="source-draft",
        run_id="wf_x",
        step="source.apply",
        status="passed",
        side_effect_level="reversible",
        compensation=comp,
    )
    assert env["compensation"] == comp


def test_evidence_http_defaults() -> None:
    ev = evidence_http("platform-control:/health", status_code=200)
    assert ev["kind"] == "http"
    assert ev["method"] == "GET"
    assert ev["target"] == "platform-control:/health"
    assert ev["status_code"] == 200
    assert ev["ok"] is True


def test_evidence_http_error() -> None:
    ev = evidence_http("platform-control:/health", status_code=503, method="POST")
    assert ev["ok"] is False
    assert ev["method"] == "POST"


def test_evidence_http_ok_override() -> None:
    ev = evidence_http("x", status_code=401, ok=True)
    assert ev["ok"] is True


def test_evidence_check_passed() -> None:
    ev = evidence_check("response_has_id", passed=True, detail="id=abc")
    assert ev["kind"] == "check"
    assert ev["name"] == "response_has_id"
    assert ev["passed"] is True
    assert ev["detail"] == "id=abc"


def test_evidence_check_failed_no_detail() -> None:
    ev = evidence_check("response_has_id", passed=False)
    assert ev["passed"] is False
    assert "detail" not in ev


def test_compensation_command() -> None:
    comp = compensation_command("wf_123", "source")
    assert comp["available"] is True
    assert "wf_123" in comp["command"]
    assert "source compensate" in comp["command"]


def test_compensation_command_default_prefix() -> None:
    comp = compensation_command("wf_abc")
    assert "source" in comp["command"]
