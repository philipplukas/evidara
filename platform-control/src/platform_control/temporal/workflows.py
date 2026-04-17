from __future__ import annotations

import asyncio
from datetime import timedelta

from temporalio import workflow
from temporalio.common import RetryPolicy

with workflow.unsafe.imports_passed_through():
    from platform_control.temporal.activities import (
        RetentionActivities,
        ReviewDrainActivities,
        ScopeShardActivities,
        WizardStateActivities,
        _sanitize_shard_key,
    )

# Maximum number of drain-poll iterations before the workflow gives up waiting.
# At a 30-minute poll interval this caps wait time at 24 hours.
_MAX_DRAIN_POLLS = 48


@workflow.defn
class ScopeShardWorkflow:
    """Per-shard discovery/extraction slice.

    A shard is typically country + jurisdiction + authority root.  Real work is
    carried out by ``ScopeShardActivities`` with retries isolated from the parent run.
    """

    @workflow.run
    async def run(
        self,
        wizard_run_id: str,
        scope_shard_key: str,
        resume_token: str | None = None,
    ) -> str:
        retry = RetryPolicy(
            maximum_attempts=5,
            backoff_coefficient=2.0,
            initial_interval=timedelta(seconds=10),
            maximum_interval=timedelta(minutes=10),
        )
        crawl_result: dict = await workflow.execute_activity_method(
            ScopeShardActivities.run_shard_crawl,
            args=[wizard_run_id, scope_shard_key, resume_token],
            start_to_close_timeout=timedelta(hours=2),
            retry_policy=retry,
        )
        await workflow.execute_activity_method(
            ScopeShardActivities.report_shard_progress,
            args=[
                wizard_run_id,
                scope_shard_key,
                {
                    "nodes_discovered": crawl_result.get("nodes_discovered", 0),
                    "records_accepted": crawl_result.get("records_accepted", 0),
                    "records_sent_to_review": crawl_result.get("records_sent_to_review", 0),
                    "fatal_error_count": crawl_result.get("fatal_error_count", 0),
                },
            ],
            start_to_close_timeout=timedelta(minutes=10),
            retry_policy=RetryPolicy(maximum_attempts=3),
        )
        return "shard_complete"


@workflow.defn
class ReviewDrainWorkflow:
    """Argilla enqueue / drain / gating workflow.

    Enqueues all pending review tasks for the run, then polls until the queue drains
    or the maximum wait window is exceeded.
    """

    @workflow.run
    async def run(self, wizard_run_id: str) -> str:
        enqueue_retry = RetryPolicy(
            maximum_attempts=5,
            backoff_coefficient=2.0,
            initial_interval=timedelta(seconds=30),
        )
        await workflow.execute_activity_method(
            ReviewDrainActivities.enqueue_pending_reviews,
            wizard_run_id,
            start_to_close_timeout=timedelta(minutes=30),
            retry_policy=enqueue_retry,
        )

        for _ in range(_MAX_DRAIN_POLLS):
            complete: bool = await workflow.execute_activity_method(
                ReviewDrainActivities.check_review_drain_complete,
                wizard_run_id,
                start_to_close_timeout=timedelta(minutes=5),
                retry_policy=RetryPolicy(maximum_attempts=3),
            )
            if complete:
                break
            await workflow.sleep(timedelta(minutes=30))

        return "drain_complete"


@workflow.defn
class WizardRunWorkflow:
    """Durable wizard run: pilot → human gate → scaled multi-shard execution.

    Platform-control remains authoritative for persisted ``WizardRun.state``;
    this workflow mirrors scaled execution via ``ScopeShardWorkflow`` and
    ``ReviewDrainWorkflow`` children so parallel work and review draining can
    grow without bloating the parent.
    """

    def __init__(self) -> None:
        self._approved = False
        self._rejected = False

    @workflow.run
    async def run(self, wizard_run_id: str) -> str:
        # --- Pilot phase ---
        # Persist PilotRun → HumanGateApproval in the DB so the API reflects
        # the gate state before the operator is prompted.
        await workflow.execute_activity_method(
            WizardStateActivities.persist_pilot_completed,
            wizard_run_id,
            start_to_close_timeout=timedelta(minutes=5),
            retry_policy=RetryPolicy(maximum_attempts=5, backoff_coefficient=2.0),
        )

        # --- Human gate ---
        await workflow.wait_condition(lambda: self._approved or self._rejected)
        if self._rejected:
            return "rejected"

        info = workflow.info()
        parent_wf_id = info.workflow_id
        tq = info.task_queue

        # --- Scaled run: fetch scope shards then fan-out in parallel ---
        shard_keys: list[str] = await workflow.execute_activity_method(
            WizardStateActivities.fetch_scope_shards,
            wizard_run_id,
            start_to_close_timeout=timedelta(minutes=5),
            retry_policy=RetryPolicy(maximum_attempts=3),
        )

        await asyncio.gather(
            *[
                workflow.execute_child_workflow(
                    ScopeShardWorkflow.run,
                    args=[wizard_run_id, key, None],
                    id=f"{parent_wf_id}__scope_shard_{_sanitize_shard_key(key)}",
                    task_queue=tq,
                )
                for key in shard_keys
            ]
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


@workflow.defn
class RetentionSweepWorkflow:
    """Thin wrapper that delegates to ``RetentionActivities.run_retention_sweep``.

    Scheduled via a Temporal Schedule (see platform-control-schedule-retention)
    so the sweep fires on a cron without anyone remembering to run
    ``pc retention sweep`` manually. Hard-delete retention is a legal
    requirement for some jurisdictions; cron enforcement matches the
    obligation's timing rather than relying on operator discipline.
    """

    @workflow.run
    async def run(self, dry_run: bool = False) -> dict:
        retry = RetryPolicy(
            maximum_attempts=3,
            backoff_coefficient=2.0,
            initial_interval=timedelta(seconds=30),
            maximum_interval=timedelta(minutes=5),
        )
        return await workflow.execute_activity_method(
            RetentionActivities.run_retention_sweep,
            dry_run,
            start_to_close_timeout=timedelta(minutes=30),
            retry_policy=retry,
        )
