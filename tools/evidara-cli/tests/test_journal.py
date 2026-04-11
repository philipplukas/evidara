"""Tests for the WorkflowJournal (ADR-0022)."""

from __future__ import annotations

import json
from pathlib import Path

import pytest

from evidara_cli.envelope import EvidenceItem, StepEnvelope
from evidara_cli.journal import WorkflowJournal


@pytest.fixture()
def journal(tmp_path: Path) -> WorkflowJournal:
    return WorkflowJournal(journal_dir=tmp_path)


def _passing_envelope(run_id: str, step: str, side_effect: str = "none") -> StepEnvelope:
    return StepEnvelope(
        ok=True,
        workflow="source",
        run_id=run_id,
        step=step,
        status="passed",
        side_effect_level=side_effect,
        inputs={"key": "val"},
        artifacts={"result": "ok"},
        evidence=[EvidenceItem(kind="http", target="http://example.com", status_code=200)],
    )


def test_create_run_returns_run_with_running_status(journal: WorkflowJournal) -> None:
    run = journal.create_run("source", inputs={"seed_url": "https://example.com"})
    assert run.status == "running"
    assert run.workflow == "source"
    assert run.run_id.startswith("wf_")
    assert run.checkpoint is None


def test_created_run_is_persisted(journal: WorkflowJournal) -> None:
    run = journal.create_run("source", inputs={})
    retrieved = journal.get_run(run.run_id)
    assert retrieved is not None
    assert retrieved.run_id == run.run_id


def test_record_step_appends_step_and_updates_checkpoint(journal: WorkflowJournal) -> None:
    run = journal.create_run("source", inputs={})
    envelope = _passing_envelope(run.run_id, "source.inspect")
    updated = journal.record_step(run.run_id, envelope)
    assert updated.checkpoint == "source.inspect"
    assert len(updated.steps) == 1
    step = updated.steps[0]
    assert step.step == "source.inspect"
    assert step.status == "passed"
    assert step.attempt == 1


def test_record_step_increments_attempt_on_retry(journal: WorkflowJournal) -> None:
    run = journal.create_run("source", inputs={})
    env1 = _passing_envelope(run.run_id, "source.inspect")
    env2 = _passing_envelope(run.run_id, "source.inspect")
    journal.record_step(run.run_id, env1)
    updated = journal.record_step(run.run_id, env2)
    assert updated.steps[-1].attempt == 2


def test_record_step_serialises_evidence_items(journal: WorkflowJournal) -> None:
    run = journal.create_run("source", inputs={})
    envelope = _passing_envelope(run.run_id, "source.inspect")
    journal.record_step(run.run_id, envelope)
    persisted = journal.get_run(run.run_id)
    assert persisted is not None
    assert persisted.steps[0].evidence[0]["kind"] == "http"
    assert persisted.steps[0].evidence[0]["status_code"] == 200


def test_close_run_sets_terminal_status(journal: WorkflowJournal) -> None:
    run = journal.create_run("source", inputs={})
    journal.close_run(run.run_id, "cancelled")
    retrieved = journal.get_run(run.run_id)
    assert retrieved is not None
    assert retrieved.status == "cancelled"
    assert retrieved.finished_at is not None


def test_close_run_raises_for_unknown_id(journal: WorkflowJournal) -> None:
    with pytest.raises(ValueError, match="not found"):
        journal.close_run("wf_does_not_exist", "cancelled")


def test_list_runs_returns_all_runs(journal: WorkflowJournal) -> None:
    journal.create_run("source", inputs={})
    journal.create_run("source", inputs={})
    runs = journal.list_runs()
    assert len(runs) == 2


def test_list_runs_filtered_by_workflow(journal: WorkflowJournal) -> None:
    journal.create_run("source", inputs={})
    journal.create_run("other", inputs={})
    runs = journal.list_runs(workflow="source")
    assert len(runs) == 1
    assert runs[0].workflow == "source"


def test_list_runs_returns_empty_list_when_dir_missing(tmp_path: Path) -> None:
    j = WorkflowJournal(journal_dir=tmp_path / "nonexistent")
    assert j.list_runs() == []


def test_last_step_artifact_returns_value(journal: WorkflowJournal) -> None:
    run = journal.create_run("source", inputs={})
    env = StepEnvelope(
        ok=True,
        workflow="source",
        run_id=run.run_id,
        step="source.apply",
        status="passed",
        side_effect_level="reversible",
        artifacts={"source_id": "src_123"},
    )
    journal.record_step(run.run_id, env)
    val = journal.last_step_artifact(run.run_id, "source.apply", "source_id")
    assert val == "src_123"


def test_last_step_artifact_returns_none_for_missing_key(journal: WorkflowJournal) -> None:
    run = journal.create_run("source", inputs={})
    env = _passing_envelope(run.run_id, "source.inspect")
    journal.record_step(run.run_id, env)
    assert journal.last_step_artifact(run.run_id, "source.inspect", "missing_key") is None


def test_run_roundtrip_through_json(journal: WorkflowJournal, tmp_path: Path) -> None:
    run = journal.create_run("source", inputs={"x": 1})
    envelope = _passing_envelope(run.run_id, "source.inspect")
    journal.record_step(run.run_id, envelope)
    # Read the raw JSON to verify structure.
    path = tmp_path / f"{run.run_id}.json"
    data = json.loads(path.read_text())
    assert data["workflow"] == "source"
    assert data["steps"][0]["step"] == "source.inspect"
    assert isinstance(data["steps"][0]["evidence"], list)
