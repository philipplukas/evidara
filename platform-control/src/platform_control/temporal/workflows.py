from __future__ import annotations

import asyncio
from dataclasses import dataclass
from datetime import timedelta
from typing import Any

from temporalio import workflow
from temporalio.common import RetryPolicy

with workflow.unsafe.imports_passed_through():
    from platform_control.domain import WizardRunState
    from platform_control.temporal.activities import (
        RescoreFromCorrectionActivities,
        RetentionActivities,
        ReviewDrainActivities,
        ScopeShardActivities,
        WizardStateActivities,
        _sanitize_shard_key,
    )


@dataclass(slots=True)
class RescoreFromCorrectionInput:
    """Input envelope for `RescoreFromCorrectionWorkflow` (#427).

    Mirrors the subset of correction fields the rescore worker needs
    to re-extract a target. The full correction row stays in the DB;
    the workflow runs against this snapshot so retries + signal-replay
    don't depend on point-in-time DB state.
    """

    correction_id: str
    target_entity_type: str
    target_entity_id: str
    payload: dict[str, Any]


# Maximum number of drain-poll iterations before the workflow gives up waiting.
# At a 30-minute poll interval this caps wait time at 24 hours.
_MAX_DRAIN_POLLS = 48

#: Versioning gate for the #560 human-gate hardening (timeout + terminal state).
#:
#: `workflow.patched` is what lets this land without breaking replay. Every
#: recorded history in `tests/data/temporal_histories/` was written by the old
#: code, which has no gate timer and no outcome activity; on replay `patched()`
#: returns False for those histories, the legacy branch runs, and the command
#: sequence still matches. New executions take the hardened branch and record the
#: marker. `tests/unit/test_temporal_replay.py` demands exactly this rather than
#: re-recording the fixtures.
_GATE_HARDENING_PATCH = "wizard-gate-timeout-and-terminal-state"

#: Fallback used when `wizard_human_gate_timeout_seconds` is not supplied at start
#: (an execution started by older code, or a workflow driven directly in a test).
_DEFAULT_GATE_TIMEOUT_SECONDS = 72 * 60 * 60


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
    """Review-queue gate: wait until operators have cleared the run's review tasks.

    Polls until every ``ReviewTask`` for the run reaches a terminal status, or the
    maximum wait window (``_MAX_DRAIN_POLLS`` × 30min = 24h) is exceeded.

    There is no enqueue step any more. Review tasks are created directly in the
    ``review_tasks`` table by the extraction path, and operators clear them in
    ``platform-control/admin`` — the queue *is* the table. The workflow used to first
    push every pending task to a hosted Argilla instance; that integration is deleted
    (ADR-0031), and it was in any case swallowing every failure and reporting
    ``drain_complete`` having enqueued nothing (#563).
    """

    @workflow.run
    async def run(self, wizard_run_id: str) -> str:
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

    **The human gate is bounded (#560).** It used to be an unbounded
    ``wait_condition``: if nobody clicked approve or reject the execution stayed
    open forever, the DB stayed at whatever the API optimistically wrote, and no
    activity ever recorded a terminal state — so "waiting on an operator" and
    "abandoned months ago" were indistinguishable in every surface. The gate now
    expires into :attr:`WizardRunState.GATE_EXPIRED`, and the workflow writes its
    own outcome at every exit. The timeout/fallback shape is the one already
    proven in ``infra/coordinator/src/coordinator/workflows.py``.
    """

    def __init__(self) -> None:
        self._approved = False
        self._rejected = False

    async def _persist_outcome(
        self,
        wizard_run_id: str,
        state: str | None,
        event: str,
        failure_reason: str | None = None,
        expected_states: list[str] | None = None,
    ) -> bool:
        """Record the workflow's own verdict. Returns whether the write landed.

        A generous retry budget on purpose. This is one small DB write, and if it
        exhausts its attempts the activity fails, the workflow fails, and the row
        is left at whatever it said before with the execution closed-failed — no
        future signal and no future timer can rescue it. That is strictly worse
        than the "parked forever" this whole change exists to remove, so the
        budget covers hours of database unavailability rather than minutes.
        """
        return await workflow.execute_activity_method(
            WizardStateActivities.persist_wizard_outcome,
            args=[wizard_run_id, state, failure_reason, event, expected_states],
            start_to_close_timeout=timedelta(minutes=5),
            retry_policy=RetryPolicy(
                maximum_attempts=20,
                backoff_coefficient=2.0,
                initial_interval=timedelta(seconds=5),
                maximum_interval=timedelta(minutes=10),
            ),
        )

    @workflow.run
    async def run(self, wizard_run_id: str, gate_timeout_seconds: int | None = None) -> str:
        # --- Pilot phase ---
        # Persist PilotRun → HumanGateApproval in the DB so the API reflects
        # the gate state before the operator is prompted.
        await workflow.execute_activity_method(
            WizardStateActivities.persist_pilot_completed,
            wizard_run_id,
            start_to_close_timeout=timedelta(minutes=5),
            retry_policy=RetryPolicy(maximum_attempts=5, backoff_coefficient=2.0),
        )

        # Everything below this line that is new to #560 is gated on the patch, so
        # histories recorded against the old code still replay. See the constant.
        gate_hardened = workflow.patched(_GATE_HARDENING_PATCH)

        # --- Human gate ---
        if gate_hardened:
            gate_timeout = timedelta(seconds=gate_timeout_seconds or _DEFAULT_GATE_TIMEOUT_SECONDS)
            try:
                await workflow.wait_condition(
                    lambda: self._approved or self._rejected,
                    timeout=gate_timeout,
                )
            except TimeoutError:
                # The fallback is always "do not scale". Auto-approving a fan-out
                # of crawls against live government portals because nobody
                # answered is the one outcome that must never be reachable.
                #
                # `expected_states` makes this a claim, not an overwrite. The timer
                # firing and an operator clicking approve are concurrent: the API
                # sends its signal and *then* writes `ScaledRun`, and the signal
                # arrives too late to be seen by the `wait_condition` we have
                # already left. Whoever claims the row first decides, and the other
                # side is told it lost — the API raises a 409 rather than
                # reporting a success that never happened.
                claimed = await self._persist_outcome(
                    wizard_run_id,
                    WizardRunState.GATE_EXPIRED.value,
                    "gate_expired",
                    failure_reason=(
                        f"Human gate expired after {int(gate_timeout.total_seconds())}s "
                        "with no approve or reject decision."
                    ),
                    expected_states=[WizardRunState.HUMAN_GATE_APPROVAL.value],
                )
                # Awaiting the activity gave any in-flight signal a workflow task
                # to land on, so `self._approved` is now current.
                if claimed or not self._approved:
                    return "gate_expired"
                # The operator got in first and the API already recorded it.
                # Honour the approval rather than discarding a decision a human
                # was told had been accepted.
                workflow.logger.info(
                    "Gate timer fired but the operator's approval had already been "
                    "recorded; scaling instead of expiring."
                )
        else:
            await workflow.wait_condition(lambda: self._approved or self._rejected)

        if self._rejected:
            if gate_hardened:
                # The API writes DiscoveryPlan when it forwards the signal, but the
                # workflow must not depend on that having happened — a rejection
                # arriving any other way left the row wherever it was.
                await self._persist_outcome(
                    wizard_run_id,
                    WizardRunState.DISCOVERY_PLAN.value,
                    "gate_rejected",
                    expected_states=[
                        WizardRunState.HUMAN_GATE_APPROVAL.value,
                        WizardRunState.DISCOVERY_PLAN.value,
                    ],
                )
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

        try:
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
        except Exception as exc:
            if gate_hardened:
                # Leave the run where it is, but say why it stopped. A failed
                # scaled run used to be indistinguishable from a running one.
                #
                # `state=None` deliberately: the run *is* in `ScaledRun`, and
                # re-stamping the state it already had would bump
                # `state_entered_at` for a transition that did not happen,
                # corrupting the state-dwell metric the battle-test scenarios
                # track. `failure_reason` is what distinguishes "scaling" from
                # "died an hour ago"; the state cannot, and adding a `Failed`
                # state is a state-machine change this PR is not making.
                await self._persist_outcome(
                    wizard_run_id,
                    None,
                    "scaled_failed",
                    failure_reason=f"Scaled run failed: {exc}",
                )
            raise

        if gate_hardened:
            # `ScaledRun -> ReviewRouting` on `scaled_completed`, guarded by
            # `allShardWorkflowsTerminal` — which is exactly what the gather above
            # having returned means. Until now nothing ever wrote this state.
            await self._persist_outcome(
                wizard_run_id,
                WizardRunState.REVIEW_ROUTING.value,
                "scaled_completed",
                expected_states=[
                    WizardRunState.SCALED_RUN.value,
                    # The API writes `ScaledRun` when it forwards the approve
                    # signal, but the workflow must not require that to have
                    # happened — the signal can arrive by other routes.
                    WizardRunState.HUMAN_GATE_APPROVAL.value,
                ],
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
class RescoreFromCorrectionWorkflow:
    """Targeted re-extraction triggered by an applied `rescore_request` correction (#427).

    Idempotency: Temporal workflow IDs are derived from the correction
    ID (`rescore-{correction_id}`), so re-firing on the same correction
    is short-circuited at start-time by `WorkflowAlreadyStartedError`.
    The workflow itself is a thin shell — the heavy lifting happens
    inside the activity (`run_targeted_rescore`), which calls the DI
    processing runtime, observes the outcome, and writes
    `rescore_outcome` + `resulting_run_id` back onto the correction's
    payload.

    Retry policy: short backoff with 3 attempts. Beyond that the
    correction is recorded as `failed` so the metrics dashboard counts
    it accurately rather than retrying forever.
    """

    @workflow.run
    async def run(self, input: RescoreFromCorrectionInput) -> dict[str, Any]:
        retry = RetryPolicy(
            maximum_attempts=3,
            backoff_coefficient=2.0,
            initial_interval=timedelta(seconds=15),
            maximum_interval=timedelta(minutes=2),
            non_retryable_error_types=["ConflictError", "NotFoundError"],
        )
        return await workflow.execute_activity_method(
            RescoreFromCorrectionActivities.run_targeted_rescore,
            input,
            start_to_close_timeout=timedelta(minutes=15),
            retry_policy=retry,
        )


@workflow.defn
class RetentionSweepWorkflow:
    """Thin wrapper that delegates to ``RetentionActivities.run_retention_sweep``.

    **Not the scheduler.** Hard-delete retention is a legal requirement in some
    jurisdictions, and this workflow only fires when a Temporal worker is running
    — which it is in no environment. So the sweep is scheduled by a Kubernetes
    CronJob (``infra/hetzner/apps/retention-sweep-cronjob.yaml``) invoking the
    ``platform-control-retention-sweep`` console script, and the Temporal Schedule
    that used to drive this workflow is gone. A cron obligation does not need
    durable execution. See ADR-0031 and docs/runbooks/retention-sweep.md.

    Kept — and pointed at the same shared implementation — so the Temporal code
    stays honest if a worker is ever deployed. If you re-add a Temporal Schedule
    for it, remove the CronJob first: two schedulers would double-sweep.
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


#: Every workflow the Temporal worker registers. Single source of truth for
#: `temporal_worker.py` and for the replay suite, which asserts that each entry
#: here has a recorded history checked in (`tests/data/temporal_histories/`).
#: Adding a workflow without a history is a test failure, on purpose: an
#: unreplayed workflow is an unguarded one.
ALL_WORKFLOWS: list[type] = [
    WizardRunWorkflow,
    ScopeShardWorkflow,
    ReviewDrainWorkflow,
    RetentionSweepWorkflow,
    RescoreFromCorrectionWorkflow,
]
