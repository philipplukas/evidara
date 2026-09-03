"""Replay coverage for every registered Temporal workflow (#564).

Replay is the whole reason to run workflows on Temporal: a worker that restarts
mid-execution must rebuild its in-memory state by re-running the workflow
function against the recorded event history, and it must reach exactly the same
commands it reached the first time. If workflow code changes in a way that
reorders, adds, or removes commands, every in-flight execution started against
the old code breaks on the next worker poll — as a non-deterministic workflow
task failure that retries forever, not as a clean error.

`grep -rn Replayer platform-control/` used to return nothing, so nothing caught
that. This module closes the gap with two layers:

* :func:`test_recorded_history_replays` — the regression guard. Replays a
  history recorded against *older* workflow code and checked into
  ``tests/data/temporal_histories/``. This is the test that fails when someone
  edits a workflow in a replay-breaking way. It needs no server, no binary and
  no network: :class:`~temporalio.worker.Replayer` re-runs the workflow purely
  in-process. So it runs on every CI run and every offline dev machine,
  unconditionally.

* :func:`test_live_execution_replays` — the recorder, and a worker-restart
  proof for the code as it stands *today*. Drives each workflow on the local
  time-skipping test server against stub activities, then replays the history it
  just produced. Marked ``temporal`` because it needs that server.

Regenerating the checked-in histories (only ever do this deliberately — a
regenerated history no longer guards the change you just made):

    cd platform-control && RECORD_TEMPORAL_HISTORIES=1 uv run pytest \
        tests/unit/test_temporal_replay.py -k live_execution

Note the activities below are stubs. Replay never calls activities — their
results are read back out of history — and the recorder only needs them to
produce a completed execution, not to do real work.
"""

from __future__ import annotations

import os
from pathlib import Path
from typing import Any

import pytest
from temporalio import activity
from temporalio.client import WorkflowHistory
from temporalio.testing import WorkflowEnvironment
from temporalio.worker import Replayer, Worker

from platform_control.temporal.workflows import (
    ALL_WORKFLOWS,
    RescoreFromCorrectionInput,
    RescoreFromCorrectionWorkflow,
    RetentionSweepWorkflow,
    ReviewDrainWorkflow,
    ScopeShardWorkflow,
    WizardRunWorkflow,
)

HISTORY_DIR = Path(__file__).resolve().parent.parent / "data" / "temporal_histories"

_TASK_QUEUE = "replay-suite"
_WIZARD_RUN_ID = "wrn_01jq7replay0000000000001"
_CORRECTION_ID = "cor_01jq7replay0000000000001"


# --- Stub activities, registered under the production activity names ----------


@activity.defn(name="persist_pilot_completed")
async def _persist_pilot_completed(wizard_run_id: str) -> None:
    return None


@activity.defn(name="persist_wizard_outcome")
async def _persist_wizard_outcome(
    wizard_run_id: str,
    state_value: str,
    failure_reason: str | None,
    event: str,
) -> None:
    return None


@activity.defn(name="fetch_scope_shards")
async def _fetch_scope_shards(wizard_run_id: str) -> list[str]:
    # Two shards, so the recorded parent history exercises the parallel
    # child-workflow fan-out rather than a degenerate single-child case.
    return ["ch/zurich", "ch/bern"]


@activity.defn(name="run_shard_crawl")
async def _run_shard_crawl(
    wizard_run_id: str,
    scope_shard_key: str,
    resume_token: str | None,
) -> dict:
    return {
        "nodes_discovered": 3,
        "records_accepted": 2,
        "records_sent_to_review": 1,
        "fatal_error_count": 0,
    }


@activity.defn(name="report_shard_progress")
async def _report_shard_progress(
    wizard_run_id: str,
    scope_shard_key: str,
    stats: dict,
) -> None:
    return None


@activity.defn(name="check_review_drain_complete")
async def _check_review_drain_complete(wizard_run_id: str) -> bool:
    return True


@activity.defn(name="run_retention_sweep")
async def _run_retention_sweep(dry_run: bool = False) -> dict:
    return {"documents_deleted": 0, "dry_run": dry_run}


@activity.defn(name="run_targeted_rescore")
async def _run_targeted_rescore(payload: Any) -> dict[str, Any]:
    return {"outcome": "unchanged", "resulting_run_id": None}


_STUB_ACTIVITIES = [
    _persist_pilot_completed,
    _persist_wizard_outcome,
    _fetch_scope_shards,
    _run_shard_crawl,
    _report_shard_progress,
    _check_review_drain_complete,
    _run_retention_sweep,
    _run_targeted_rescore,
]


def _history_path(workflow_cls: type) -> Path:
    return HISTORY_DIR / f"{workflow_cls.__name__}.json"


async def _execute(env: WorkflowEnvironment, workflow_cls: type) -> WorkflowHistory:
    """Run one workflow to completion on the test server and return its history."""
    workflow_id = f"replay-{workflow_cls.__name__}"

    if workflow_cls is WizardRunWorkflow:
        handle = await env.client.start_workflow(
            WizardRunWorkflow.run,
            _WIZARD_RUN_ID,
            id=workflow_id,
            task_queue=_TASK_QUEUE,
        )
        # The workflow parks on `wait_condition(approved or rejected)`; the
        # signal is what makes the recorded history cover the human gate.
        await handle.signal(WizardRunWorkflow.approve, "pilot quality ok")
        assert await handle.result() == "scaled"
    elif workflow_cls is ScopeShardWorkflow:
        handle = await env.client.start_workflow(
            ScopeShardWorkflow.run,
            args=[_WIZARD_RUN_ID, "ch/zurich", None],
            id=workflow_id,
            task_queue=_TASK_QUEUE,
        )
        assert await handle.result() == "shard_complete"
    elif workflow_cls is ReviewDrainWorkflow:
        handle = await env.client.start_workflow(
            ReviewDrainWorkflow.run,
            _WIZARD_RUN_ID,
            id=workflow_id,
            task_queue=_TASK_QUEUE,
        )
        assert await handle.result() == "drain_complete"
    elif workflow_cls is RetentionSweepWorkflow:
        handle = await env.client.start_workflow(
            RetentionSweepWorkflow.run,
            True,
            id=workflow_id,
            task_queue=_TASK_QUEUE,
        )
        assert (await handle.result())["dry_run"] is True
    elif workflow_cls is RescoreFromCorrectionWorkflow:
        handle = await env.client.start_workflow(
            RescoreFromCorrectionWorkflow.run,
            RescoreFromCorrectionInput(
                correction_id=_CORRECTION_ID,
                target_entity_type="document",
                target_entity_id="doc_01jq7replay000000000001",
                payload={"reason_code": "low_quality_extractions"},
            ),
            id=workflow_id,
            task_queue=_TASK_QUEUE,
        )
        assert (await handle.result())["outcome"] == "unchanged"
    else:  # pragma: no cover - guarded by test_every_workflow_is_covered
        raise AssertionError(
            f"{workflow_cls.__name__} has no replay driver. Add one to `_execute` so "
            "the workflow gets a recorded history, or it ships unguarded."
        )

    return await handle.fetch_history()


def test_every_registered_workflow_has_a_recorded_history() -> None:
    """No workflow may ship without a checked-in history to replay against."""
    missing = [wf.__name__ for wf in ALL_WORKFLOWS if not _history_path(wf).exists()]
    assert not missing, (
        f"No recorded Temporal history for: {', '.join(missing)}. Add a driver to "
        "`_execute` and regenerate with RECORD_TEMPORAL_HISTORIES=1 (see module docstring)."
    )


@pytest.mark.asyncio
@pytest.mark.parametrize("workflow_cls", ALL_WORKFLOWS, ids=lambda cls: cls.__name__)
async def test_recorded_history_replays(workflow_cls: type) -> None:
    """Current workflow code must replay a history recorded against older code.

    A failure here means the change under review is not replay-safe: every
    in-flight execution of this workflow would wedge on a non-determinism error
    the moment a worker running the new code picked it up. Fix it with a
    versioning gate (`workflow.patched` / `workflow.deprecate_patch`) — do not
    "fix" it by re-recording the history.
    """
    history = WorkflowHistory.from_json(
        f"replay-{workflow_cls.__name__}",
        _history_path(workflow_cls).read_text(),
    )
    await Replayer(workflows=ALL_WORKFLOWS).replay_workflow(history)


@pytest.mark.temporal
@pytest.mark.asyncio
@pytest.mark.parametrize("workflow_cls", ALL_WORKFLOWS, ids=lambda cls: cls.__name__)
async def test_live_execution_replays(
    workflow_cls: type,
    temporal_env: WorkflowEnvironment,
) -> None:
    """Execute the workflow for real, then replay the history it just wrote.

    This is the worker-restart proof: replaying a fresh history through a fresh
    `Replayer` is exactly what a restarted worker does when it picks the
    execution back up. Doubles as the recorder for the checked-in histories.
    """
    async with Worker(
        temporal_env.client,
        task_queue=_TASK_QUEUE,
        workflows=ALL_WORKFLOWS,
        activities=_STUB_ACTIVITIES,
    ):
        history = await _execute(temporal_env, workflow_cls)

    await Replayer(workflows=ALL_WORKFLOWS).replay_workflow(history)

    if os.environ.get("RECORD_TEMPORAL_HISTORIES") == "1":
        HISTORY_DIR.mkdir(parents=True, exist_ok=True)
        _history_path(workflow_cls).write_text(history.to_json() + "\n")
