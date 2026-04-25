from __future__ import annotations

import asyncio
from datetime import timedelta

from temporalio import workflow
from temporalio.common import RetryPolicy

with workflow.unsafe.imports_passed_through():
    from platform_control.temporal.activities import (
        RescoreActivities,
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
class RescoreCorrectionWorkflow:
    """Targeted re-extraction triggered by a correction (issue #427).

    The workflow is idempotent on ``(source_correction_id, target_entity_id)``
    — see ``rescore_workflow_id`` in ``correction_service`` for the id
    derivation. Repeated calls with the same arguments collapse to the same
    Temporal workflow execution.

    Activities run sequentially:

    1. ``resolve_correction`` — load the rescore + source rows.
    2. ``load_target_entity`` — fetch the baseline snapshot.
    3. ``invoke_targeted_extraction`` — call into document-intelligence.
    4. ``diff_against_baseline`` — classify the outcome.
    5. ``record_outcome`` — persist + log + emit metric.
    """

    @workflow.run
    async def run(self, rescore_correction_id: str) -> str:
        retry = RetryPolicy(
            maximum_attempts=3,
            backoff_coefficient=2.0,
            initial_interval=timedelta(seconds=10),
            maximum_interval=timedelta(minutes=2),
        )
        try:
            resolved: dict = await workflow.execute_activity_method(
                RescoreActivities.resolve_correction,
                rescore_correction_id,
                start_to_close_timeout=timedelta(minutes=2),
                retry_policy=retry,
            )
            target_entity_type = resolved["target_entity_type"]
            target_entity_id = resolved["target_entity_id"]
            source_payload = resolved.get("source_payload") or {}
            dry_run = bool(resolved.get("dry_run", False))

            baseline_result: dict = await workflow.execute_activity_method(
                RescoreActivities.load_target_entity,
                args=[target_entity_type, target_entity_id, source_payload],
                start_to_close_timeout=timedelta(minutes=2),
                retry_policy=retry,
            )
            baseline = baseline_result.get("baseline") or {}

            extraction_result: dict = await workflow.execute_activity_method(
                RescoreActivities.invoke_targeted_extraction,
                args=[
                    target_entity_type,
                    target_entity_id,
                    baseline,
                    source_payload,
                    dry_run,
                ],
                start_to_close_timeout=timedelta(minutes=15),
                retry_policy=retry,
            )

            diffed: dict = await workflow.execute_activity_method(
                RescoreActivities.diff_against_baseline,
                extraction_result,
                start_to_close_timeout=timedelta(minutes=2),
                retry_policy=RetryPolicy(maximum_attempts=2),
            )
            outcome = str(diffed.get("outcome", "failed"))
            await workflow.execute_activity_method(
                RescoreActivities.record_outcome,
                args=[
                    rescore_correction_id,
                    outcome,
                    diffed.get("diff", {}),
                    diffed.get("extraction_id"),
                    None,  # resulting_run_id is set when DI exposes it
                    diffed.get("error"),
                ],
                start_to_close_timeout=timedelta(minutes=2),
                retry_policy=RetryPolicy(maximum_attempts=3),
            )
            return outcome
        except Exception as exc:  # noqa: BLE001 — final-attempt failure
            await workflow.execute_activity_method(
                RescoreActivities.record_outcome,
                args=[
                    rescore_correction_id,
                    "failed",
                    {},
                    None,
                    None,
                    str(exc),
                ],
                start_to_close_timeout=timedelta(minutes=2),
                retry_policy=RetryPolicy(maximum_attempts=3),
            )
            raise


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
