from __future__ import annotations

from evidara_cli.journal import LocalJournal, WorkflowRun, WorkflowStepRun


def _make_step(run_id: str = "wf_001", step: str = "source.inspect") -> WorkflowStepRun:
    return WorkflowStepRun(
        run_id=run_id,
        step=step,
        attempt=1,
        side_effect_level="none",
        status="passed",
        inputs={"source_id": None},
        artifacts={},
        evidence=[{"kind": "http", "target": "pc:/health", "status_code": 200}],
        correlation_id=None,
    )


def test_create_run_and_retrieve() -> None:
    j = LocalJournal()
    run = j.create_run("wf_001", "source-draft", requested_by="agent", inputs={"k": "v"})
    assert isinstance(run, WorkflowRun)
    assert run.run_id == "wf_001"
    assert run.workflow == "source-draft"
    assert run.status == "running"
    assert run.inputs == {"k": "v"}
    assert j.get_run("wf_001") is run


def test_get_run_missing_returns_none() -> None:
    j = LocalJournal()
    assert j.get_run("nonexistent") is None


def test_record_step_and_retrieve() -> None:
    j = LocalJournal()
    j.create_run("wf_001", "source-draft")
    step = _make_step("wf_001", "source.inspect")
    j.record_step(step)
    steps = j.get_steps("wf_001")
    assert len(steps) == 1
    assert steps[0].step == "source.inspect"
    assert steps[0].finished_at is not None


def test_record_multiple_steps() -> None:
    j = LocalJournal()
    j.create_run("wf_001", "source-draft")
    j.record_step(_make_step("wf_001", "source.inspect"))
    j.record_step(_make_step("wf_001", "source.propose"))
    steps = j.get_steps("wf_001")
    assert len(steps) == 2
    assert steps[0].step == "source.inspect"
    assert steps[1].step == "source.propose"


def test_get_steps_filters_by_run_id() -> None:
    j = LocalJournal()
    j.create_run("wf_001", "source-draft")
    j.create_run("wf_002", "search-verify")
    j.record_step(_make_step("wf_001", "source.inspect"))
    j.record_step(_make_step("wf_002", "search.inspect"))
    assert len(j.get_steps("wf_001")) == 1
    assert len(j.get_steps("wf_002")) == 1


def test_complete_run_updates_status() -> None:
    j = LocalJournal()
    j.create_run("wf_001", "source-draft")
    j.complete_run("wf_001", status="passed", checkpoint="source.verify")
    run = j.get_run("wf_001")
    assert run is not None
    assert run.status == "passed"
    assert run.checkpoint == "source.verify"
    assert run.finished_at is not None


def test_complete_run_missing_is_no_op() -> None:
    j = LocalJournal()
    j.complete_run("nonexistent", status="passed")  # should not raise


def test_to_evidence_summary_basic() -> None:
    j = LocalJournal()
    j.create_run("wf_001", "source-draft", requested_by="agent")
    j.record_step(_make_step("wf_001", "source.inspect"))
    j.record_step(_make_step("wf_001", "source.apply"))
    j.complete_run("wf_001", status="passed", checkpoint="source.apply")

    summary = j.to_evidence_summary("wf_001")
    assert summary["run_id"] == "wf_001"
    assert summary["workflow"] == "source-draft"
    assert summary["status"] == "passed"
    assert summary["step_count"] == 2
    assert summary["checkpoint"] == "source.apply"
    assert len(summary["steps"]) == 2
    assert summary["steps"][0]["step"] == "source.inspect"
    assert summary["steps"][1]["evidence_count"] == 1


def test_to_evidence_summary_missing_run() -> None:
    j = LocalJournal()
    summary = j.to_evidence_summary("nonexistent")
    assert summary["status"] == "unknown"
    assert summary["step_count"] == 0
