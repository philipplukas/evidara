"""Tests for evidara workflow source / run commands (ADR-0022)."""

from __future__ import annotations

from pathlib import Path
from unittest.mock import MagicMock, patch

import pytest
import typer

from evidara_cli.journal import WorkflowJournal
from evidara_cli.workflow_cmd import (
    run_cancel,
    run_evidence,
    run_status,
    source_apply,
    source_compensate,
    source_inspect,
    source_propose,
    source_verify,
)

# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------


def _journal(tmp_path: Path) -> WorkflowJournal:
    return WorkflowJournal(journal_dir=tmp_path)


def _patch_journal(tmp_path: Path):
    """Patch _default_journal to use a temp directory."""
    return patch("evidara_cli.workflow_cmd._default_journal", return_value=_journal(tmp_path))


# ---------------------------------------------------------------------------
# source inspect
# ---------------------------------------------------------------------------


@patch("evidara_cli.workflow_cmd._emit_envelope")
@patch("evidara_cli.workflow_cmd.request_json")
@patch("evidara_cli.workflow_cmd.request_status", return_value=200)
@patch("evidara_cli.workflow_cmd.platform_control_base_url", return_value="http://pc.test")
def test_source_inspect_ok(
    _pc: object,
    _status: object,
    request_json_mock: MagicMock,
    emit_mock: MagicMock,
    tmp_path: Path,
) -> None:
    request_json_mock.return_value = {"items": [{"id": "src_1"}, {"id": "src_2"}]}
    with _patch_journal(tmp_path):
        source_inspect(source_id=None, run_id=None, human=False, correlation_id=None)
    emit_mock.assert_called_once()
    envelope = emit_mock.call_args.args[0]
    assert envelope.ok is True
    assert envelope.step == "source.inspect"
    assert envelope.side_effect_level == "none"
    assert envelope.status == "passed"
    assert envelope.artifacts["source_count"] == 2
    assert "propose" in envelope.next_actions


@patch("evidara_cli.workflow_cmd._emit_envelope")
@patch("evidara_cli.workflow_cmd.request_status", return_value=503)
@patch("evidara_cli.workflow_cmd.platform_control_base_url", return_value="http://pc.test")
def test_source_inspect_health_fail_exits_1(
    _pc: object,
    _status: object,
    emit_mock: MagicMock,
    tmp_path: Path,
) -> None:
    with _patch_journal(tmp_path):
        with pytest.raises(typer.Exit) as exc_info:
            source_inspect(source_id=None, run_id=None, human=False, correlation_id=None)
    assert exc_info.value.exit_code == 1
    envelope = emit_mock.call_args.args[0]
    assert envelope.ok is False
    assert envelope.status == "failed_retriable"


@patch("evidara_cli.workflow_cmd._emit_envelope")
@patch("evidara_cli.workflow_cmd.request_json")
@patch("evidara_cli.workflow_cmd.request_status", return_value=200)
@patch("evidara_cli.workflow_cmd.platform_control_base_url", return_value="http://pc.test")
def test_source_inspect_continues_existing_run(
    _pc: object,
    _status: object,
    request_json_mock: MagicMock,
    emit_mock: MagicMock,
    tmp_path: Path,
) -> None:
    journal = _journal(tmp_path)
    run = journal.create_run("source", inputs={})
    request_json_mock.return_value = {"items": []}
    with patch("evidara_cli.workflow_cmd._default_journal", return_value=journal):
        source_inspect(source_id=None, run_id=run.run_id, human=False, correlation_id=None)
    envelope = emit_mock.call_args.args[0]
    assert envelope.run_id == run.run_id


# ---------------------------------------------------------------------------
# source propose
# ---------------------------------------------------------------------------


@patch("evidara_cli.workflow_cmd._emit_envelope")
def test_source_propose_creates_spec_without_api(emit_mock: MagicMock, tmp_path: Path) -> None:
    with _patch_journal(tmp_path):
        source_propose(
            seed_url="https://example.com/legal",
            run_id=None,
            use_dspy=False,
            human=False,
            correlation_id=None,
        )
    emit_mock.assert_called_once()
    envelope = emit_mock.call_args.args[0]
    assert envelope.ok is True
    assert envelope.step == "source.propose"
    assert envelope.side_effect_level == "none"
    assert envelope.status == "passed"
    spec = envelope.artifacts["proposed_spec"]
    assert "name" in spec
    assert spec["seed_url"] == "https://example.com/legal"
    assert "apply" in envelope.next_actions


@patch("evidara_cli.workflow_cmd._emit_envelope")
def test_source_propose_uses_existing_run_id(emit_mock: MagicMock, tmp_path: Path) -> None:
    journal = _journal(tmp_path)
    run = journal.create_run("source", inputs={})
    with patch("evidara_cli.workflow_cmd._default_journal", return_value=journal):
        source_propose(
            seed_url="https://example.com",
            run_id=run.run_id,
            use_dspy=False,
            human=False,
            correlation_id=None,
        )
    envelope = emit_mock.call_args.args[0]
    assert envelope.run_id == run.run_id


@patch("evidara_cli.workflow_cmd._emit_envelope")
def test_source_propose_with_dspy_flag_falls_back_gracefully(
    emit_mock: MagicMock, tmp_path: Path
) -> None:
    """--use-dspy falls back to rule-based when dspy is not installed."""
    with _patch_journal(tmp_path):
        source_propose(
            seed_url="https://example.com",
            run_id=None,
            use_dspy=True,
            human=False,
            correlation_id=None,
        )
    envelope = emit_mock.call_args.args[0]
    assert envelope.ok is True
    spec = envelope.artifacts["proposed_spec"]
    assert "name" in spec


# ---------------------------------------------------------------------------
# source apply
# ---------------------------------------------------------------------------


@patch("evidara_cli.workflow_cmd._emit_envelope")
@patch("evidara_cli.workflow_cmd.request_json")
@patch("evidara_cli.workflow_cmd.platform_control_base_url", return_value="http://pc.test")
def test_source_apply_ok(
    _pc: object,
    request_json_mock: MagicMock,
    emit_mock: MagicMock,
    tmp_path: Path,
) -> None:
    journal = _journal(tmp_path)
    run = journal.create_run("source", inputs={})
    request_json_mock.return_value = {"source_id": "src_new", "source_version_id": "sv_new"}
    with patch("evidara_cli.workflow_cmd._default_journal", return_value=journal):
        source_apply(
            run_id=run.run_id,
            source_name="test-source",
            seed_url="https://example.com",
            human=False,
            correlation_id=None,
        )
    emit_mock.assert_called_once()
    envelope = emit_mock.call_args.args[0]
    assert envelope.ok is True
    assert envelope.step == "source.apply"
    assert envelope.side_effect_level == "reversible"
    assert envelope.artifacts["source_id"] == "src_new"
    assert envelope.compensation is not None
    assert envelope.compensation.available is True
    assert "verify" in envelope.next_actions


@patch("evidara_cli.workflow_cmd._emit_envelope")
@patch(
    "evidara_cli.workflow_cmd.request_json",
    side_effect=Exception("connection refused"),
)
@patch("evidara_cli.workflow_cmd.platform_control_base_url", return_value="http://pc.test")
def test_source_apply_api_failure_exits_1(
    _pc: object,
    _rj: object,
    emit_mock: MagicMock,
    tmp_path: Path,
) -> None:
    from evidara_cli.client import HttpJsonError

    journal = _journal(tmp_path)
    run = journal.create_run("source", inputs={})
    with patch("evidara_cli.workflow_cmd._default_journal", return_value=journal):
        with patch(
            "evidara_cli.workflow_cmd.request_json",
            side_effect=HttpJsonError("err", status_code=500, body="oops"),
        ):
            with pytest.raises(typer.Exit) as exc_info:
                source_apply(
                    run_id=run.run_id,
                    source_name=None,
                    seed_url=None,
                    human=False,
                    correlation_id=None,
                )
    assert exc_info.value.exit_code == 1
    envelope = emit_mock.call_args.args[0]
    assert envelope.ok is False
    assert envelope.status == "failed_retriable"


# ---------------------------------------------------------------------------
# source verify
# ---------------------------------------------------------------------------


@patch("evidara_cli.workflow_cmd._emit_envelope")
@patch("evidara_cli.workflow_cmd.request_json")
@patch("evidara_cli.workflow_cmd.platform_control_base_url", return_value="http://pc.test")
def test_source_verify_ok(
    _pc: object,
    request_json_mock: MagicMock,
    emit_mock: MagicMock,
    tmp_path: Path,
) -> None:
    journal = _journal(tmp_path)
    run = journal.create_run("source", inputs={})
    request_json_mock.return_value = {
        "source_id": "src_001",
        "id": "src_001",
        "name": "Test Source",
        "status": "draft",
    }
    with patch("evidara_cli.workflow_cmd._default_journal", return_value=journal):
        source_verify(
            run_id=run.run_id,
            source_id="src_001",
            human=False,
            correlation_id=None,
        )
    envelope = emit_mock.call_args.args[0]
    assert envelope.ok is True
    assert envelope.step == "source.verify"
    assert envelope.side_effect_level == "none"
    assert envelope.artifacts["detail_checks"]["name_present"] is True


@patch("evidara_cli.workflow_cmd._emit_envelope")
def test_source_verify_requires_run_id_or_source_id(
    _emit: MagicMock, tmp_path: Path
) -> None:
    with _patch_journal(tmp_path):
        with pytest.raises(typer.Exit) as exc_info:
            source_verify(run_id=None, source_id=None, human=False, correlation_id=None)
    assert exc_info.value.exit_code == 1


# ---------------------------------------------------------------------------
# source compensate
# ---------------------------------------------------------------------------


@patch("evidara_cli.workflow_cmd._emit_envelope")
def test_source_compensate_no_reversible_steps(emit_mock: MagicMock, tmp_path: Path) -> None:
    journal = _journal(tmp_path)
    run = journal.create_run("source", inputs={})
    with patch("evidara_cli.workflow_cmd._default_journal", return_value=journal):
        source_compensate(run_id=run.run_id, human=False, correlation_id=None)
    envelope = emit_mock.call_args.args[0]
    assert envelope.ok is True
    assert envelope.status == "passed"
    assert "No reversible" in envelope.artifacts["note"]


@patch("evidara_cli.workflow_cmd._emit_envelope")
@patch("evidara_cli.workflow_cmd.request_json")
@patch("evidara_cli.workflow_cmd.platform_control_base_url", return_value="http://pc.test")
def test_source_compensate_rejects_source_version(
    _pc: object,
    request_json_mock: MagicMock,
    emit_mock: MagicMock,
    tmp_path: Path,
) -> None:
    from evidara_cli.envelope import CompensationRef, StepDecision, StepEnvelope

    journal = _journal(tmp_path)
    run = journal.create_run("source", inputs={})
    # Simulate a prior apply step with a source_version_id.
    apply_env = StepEnvelope(
        ok=True,
        workflow="source",
        run_id=run.run_id,
        step="source.apply",
        status="passed",
        side_effect_level="reversible",
        artifacts={"source_id": "src_001", "source_version_id": "sv_001"},
        decision=StepDecision("verify", "ok"),
        compensation=CompensationRef(available=True),
    )
    journal.record_step(run.run_id, apply_env)
    request_json_mock.return_value = {"ok": True}

    with patch("evidara_cli.workflow_cmd._default_journal", return_value=journal):
        source_compensate(run_id=run.run_id, human=False, correlation_id=None)

    envelope = emit_mock.call_args.args[0]
    assert envelope.ok is True
    assert envelope.status == "compensated"
    assert envelope.artifacts["source_version_id"] == "sv_001"
    # Run should be closed as "compensated".
    final_run = journal.get_run(run.run_id)
    assert final_run is not None
    assert final_run.status == "compensated"


# ---------------------------------------------------------------------------
# run management commands
# ---------------------------------------------------------------------------


@patch("evidara_cli.workflow_cmd._emit_envelope")
def test_run_status_outputs_run_summary(
    _emit: MagicMock, tmp_path: Path, capsys: pytest.CaptureFixture[str]
) -> None:
    journal = _journal(tmp_path)
    run = journal.create_run("source", inputs={})
    with patch("evidara_cli.workflow_cmd._default_journal", return_value=journal):
        run_status(run_id=run.run_id, human=False)
    import json

    captured = capsys.readouterr()
    data = json.loads(captured.out)
    assert data["run_id"] == run.run_id
    assert data["status"] == "running"


@patch("evidara_cli.workflow_cmd._emit_envelope")
def test_run_cancel_closes_run(
    _emit: MagicMock, tmp_path: Path, capsys: pytest.CaptureFixture[str]
) -> None:
    journal = _journal(tmp_path)
    run = journal.create_run("source", inputs={})
    with patch("evidara_cli.workflow_cmd._default_journal", return_value=journal):
        run_cancel(run_id=run.run_id, human=False)
    import json

    captured = capsys.readouterr()
    data = json.loads(captured.out)
    assert data["ok"] is True
    assert data["status"] == "cancelled"


@patch("evidara_cli.workflow_cmd._emit_envelope")
def test_run_evidence_shows_steps(
    _emit: MagicMock, tmp_path: Path, capsys: pytest.CaptureFixture[str]
) -> None:
    from evidara_cli.envelope import StepEnvelope

    journal = _journal(tmp_path)
    run = journal.create_run("source", inputs={})
    env = StepEnvelope(
        ok=True,
        workflow="source",
        run_id=run.run_id,
        step="source.inspect",
        status="passed",
        side_effect_level="none",
        artifacts={"source_count": 5},
    )
    journal.record_step(run.run_id, env)
    with patch("evidara_cli.workflow_cmd._default_journal", return_value=journal):
        run_evidence(run_id=run.run_id, human=False)
    import json

    captured = capsys.readouterr()
    data = json.loads(captured.out)
    assert len(data["steps"]) == 1
    assert data["steps"][0]["step"] == "source.inspect"
