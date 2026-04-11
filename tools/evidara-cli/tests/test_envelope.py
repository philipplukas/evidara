"""Tests for the StepEnvelope schema (ADR-0022)."""

from __future__ import annotations

from evidara_cli.envelope import (
    CompensationRef,
    EvidenceItem,
    StepDecision,
    StepEnvelope,
)


def test_evidence_item_to_dict_omits_none() -> None:
    item = EvidenceItem(kind="http", target="http://example.com", status_code=200)
    d = item.to_dict()
    assert d == {"kind": "http", "target": "http://example.com", "status_code": 200}
    assert "detail" not in d


def test_evidence_item_to_dict_includes_detail() -> None:
    item = EvidenceItem(kind="count", target="sources", detail="42")
    d = item.to_dict()
    assert d["detail"] == "42"
    assert "status_code" not in d


def test_compensation_ref_to_dict_omits_none() -> None:
    ref = CompensationRef(
        available=True,
        command="evidara workflow source compensate --run-id wf_123",
    )
    d = ref.to_dict()
    assert d["available"] is True
    assert d["command"] == "evidara workflow source compensate --run-id wf_123"
    assert "run_id" not in d


def test_step_envelope_to_dict_minimal() -> None:
    env = StepEnvelope(
        ok=True,
        workflow="source",
        run_id="wf_123",
        step="source.inspect",
        status="passed",
        side_effect_level="none",
    )
    d = env.to_dict()
    assert d["ok"] is True
    assert d["workflow"] == "source"
    assert d["run_id"] == "wf_123"
    assert d["step"] == "source.inspect"
    assert d["status"] == "passed"
    assert d["side_effect_level"] == "none"
    assert d["evidence"] == []
    assert d["next_actions"] == []
    assert d["decision"] is None
    assert d["compensation"] is None


def test_step_envelope_to_dict_full() -> None:
    env = StepEnvelope(
        ok=True,
        workflow="source",
        run_id="wf_abc",
        step="source.apply",
        status="passed",
        side_effect_level="reversible",
        inputs={"seed_url": "https://example.com"},
        artifacts={"source_id": "src_001"},
        evidence=[
            EvidenceItem(
                kind="http",
                target="platform-control:/v1/sources/with-version",
                status_code=201,
            )
        ],
        decision=StepDecision(recommended_action="verify", reason="Draft created."),
        next_actions=["verify"],
        compensation=CompensationRef(
            available=True,
            command="evidara workflow source compensate --run-id wf_abc",
        ),
    )
    d = env.to_dict()
    assert d["side_effect_level"] == "reversible"
    assert d["artifacts"]["source_id"] == "src_001"
    assert d["evidence"][0]["status_code"] == 201
    assert d["decision"]["recommended_action"] == "verify"
    assert d["compensation"]["available"] is True
    assert d["next_actions"] == ["verify"]
