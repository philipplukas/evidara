from __future__ import annotations

from datetime import timedelta

from temporalio import workflow


@workflow.defn
class ScopeShardWorkflow:
    """Per-shard discovery/extraction slice (stub: durable placeholder for TAR-108).

    A shard is typically country + jurisdiction + authority root; real work becomes
    activities (crawl, extract, rollup) with retries isolated from the parent run.
    """

    @workflow.run
    async def run(self, wizard_run_id: str, scope_shard_key: str) -> str:
        del wizard_run_id, scope_shard_key
        await workflow.sleep(timedelta(seconds=0))
        return "shard_complete"


@workflow.defn
class ReviewDrainWorkflow:
    """Argilla enqueue / drain / gating (stub: durable placeholder for TAR-108)."""

    @workflow.run
    async def run(self, wizard_run_id: str) -> str:
        del wizard_run_id
        await workflow.sleep(timedelta(seconds=0))
        return "drain_complete"


@workflow.defn
class WizardRunWorkflow:
    """Durable wizard run: pilot placeholder, human gate, then child workflows.

    Platform-control remains authoritative for persisted `WizardRun.state`; this workflow
    mirrors scaled execution via `ScopeShardWorkflow` and `ReviewDrainWorkflow` children
    so parallel work and review draining can grow without bloating the parent.
    """

    def __init__(self) -> None:
        self._approved = False
        self._rejected = False

    @workflow.run
    async def run(self, wizard_run_id: str) -> str:
        await workflow.sleep(timedelta(seconds=0))
        await workflow.wait_condition(lambda: self._approved or self._rejected)
        if self._rejected:
            return "rejected"

        info = workflow.info()
        parent_wf_id = info.workflow_id
        tq = info.task_queue

        await workflow.execute_child_workflow(
            ScopeShardWorkflow.run,
            args=[wizard_run_id, "pilot-shard"],
            id=f"{parent_wf_id}__scope_shard_pilot",
            task_queue=tq,
        )
        await workflow.execute_child_workflow(
            ReviewDrainWorkflow.run,
            args=[wizard_run_id],
            id=f"{parent_wf_id}__review_drain",
            task_queue=tq,
        )
        return "scaled"

    @workflow.signal
    def approve(self, reason: str | None = None) -> None:
        del reason
        self._approved = True

    @workflow.signal
    def reject(self, reason: str | None = None) -> None:
        del reason
        self._rejected = True
