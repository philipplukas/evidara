"""The wizard human gate has a deadline and a terminal state (#560).

Before this, `WizardRunWorkflow` parked on an unbounded
`wait_condition(lambda: self._approved or self._rejected)`. If nobody clicked
approve or reject the execution stayed open forever, and — separately — no
activity ever wrote a terminal wizard state, so the row kept whatever the API
optimistically set at signal time no matter what the workflow did afterwards.
"Waiting on an operator", "abandoned in March", and "failed an hour ago" were the
same row.

These tests drive the real workflow against the time-skipping Temporal test
server with the real activities, so the deadline is exercised as a durable timer
rather than asserted about in the abstract.
"""

from __future__ import annotations

import asyncio
import os
import sqlite3

import pytest
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession, async_sessionmaker
from temporalio.testing import WorkflowEnvironment
from temporalio.worker import Worker

from platform_control.domain import WizardRunState
from platform_control.errors import ConflictError, InvalidStateTransitionError
from platform_control.models.wizard_project import WizardProject
from platform_control.models.wizard_run import WizardRun
from platform_control.models.wizard_run_ledger import WizardRunLedger
from platform_control.schemas.wizard import CreateWizardProjectRequest
from platform_control.services.orchestrator import InMemoryOrchestrator, TemporalOrchestrator
from platform_control.services.wizard_service import WizardService
from platform_control.temporal.activities import (
    ReviewDrainActivities,
    ScopeShardActivities,
    WizardStateActivities,
)
from platform_control.temporal.workflows import (
    ReviewDrainWorkflow,
    ScopeShardWorkflow,
    WizardRunWorkflow,
)


def _sqlite_path() -> str:
    """Filesystem path behind the test session factory's SQLite URL."""
    return os.environ["PLATFORM_CONTROL_DATABASE_URL"].removeprefix("sqlite+aiosqlite:///")


#: Short enough to read as a deadline, long enough that nothing races it. The
#: time-skipping server fast-forwards the timer, so the wall clock never waits.
GATE_TIMEOUT_SECONDS = 4 * 60 * 60


def _worker(env: WorkflowEnvironment, session_maker: async_sessionmaker[AsyncSession]) -> Worker:
    state_acts = WizardStateActivities(session_factory=session_maker)
    shard_acts = ScopeShardActivities(session_factory=session_maker)
    drain_acts = ReviewDrainActivities(session_factory=session_maker)
    return Worker(
        env.client,
        task_queue="wizard-gate",
        workflows=[WizardRunWorkflow, ScopeShardWorkflow, ReviewDrainWorkflow],
        activities=[
            state_acts.persist_pilot_completed,
            state_acts.persist_wizard_outcome,
            state_acts.fetch_scope_shards,
            shard_acts.run_shard_crawl,
            shard_acts.report_shard_progress,
            drain_acts.check_review_drain_complete,
        ],
    )


async def _start_run_at_the_gate(
    env: WorkflowEnvironment,
    session_maker: async_sessionmaker[AsyncSession],
    name: str,
) -> tuple[TemporalOrchestrator, str, str]:
    """Start a wizard run and wait until the workflow is parked on the gate."""
    orchestrator = TemporalOrchestrator(
        namespace="default",
        task_queue="wizard-gate",
        client=env.client,
        human_gate_timeout_seconds=GATE_TIMEOUT_SECONDS,
    )
    async with session_maker() as session:
        service = WizardService(session, orchestrator)
        project = await service.create_project(CreateWizardProjectRequest(name=name))
        await service.update_scope(project.wizard_project_id, {"domains": ["example.ch"]})
        await service.update_discovery_plan(
            project.wizard_project_id, {"seed_urls": ["https://example.ch"]}
        )
        run = await service.start_pilot_run(project.wizard_project_id)
        wizard_run_id, workflow_id = run.wizard_run_id, run.workflow_id

    assert workflow_id is not None
    async with session_maker() as session:
        for _ in range(200):
            await asyncio.sleep(0)
            session.expire_all()
            current = await session.get(WizardRun, wizard_run_id)
            if current is not None and current.state is WizardRunState.HUMAN_GATE_APPROVAL:
                break
        else:  # pragma: no cover - the gate never opened
            raise AssertionError("workflow never reached the human gate")

    return orchestrator, wizard_run_id, workflow_id


@pytest.mark.asyncio
@pytest.mark.temporal
async def test_an_unanswered_gate_expires_instead_of_parking_forever(
    session_maker: async_sessionmaker[AsyncSession],
    temporal_env: WorkflowEnvironment,
) -> None:
    """Nobody signals. The workflow must end, and the DB must say why."""
    async with _worker(temporal_env, session_maker):
        _, wizard_run_id, workflow_id = await _start_run_at_the_gate(
            temporal_env, session_maker, "gate expiry"
        )

        handle = temporal_env.client.get_workflow_handle(workflow_id)
        # Explicitly advance past the deadline rather than relying on the
        # test server's implicit skipping, so the assertion below is about the
        # gate timer and not about how long the poll happened to take.
        await temporal_env.sleep(GATE_TIMEOUT_SECONDS + 60)
        assert await handle.result() == "gate_expired"

    async with session_maker() as session:
        run = await session.get(WizardRun, wizard_run_id)
        assert run is not None
        assert run.state is WizardRunState.GATE_EXPIRED
        assert run.failure_reason is not None
        assert str(GATE_TIMEOUT_SECONDS) in run.failure_reason

        ledger = await session.scalar(
            select(WizardRunLedger).where(WizardRunLedger.wizard_run_id == wizard_run_id)
        )
        assert ledger is not None
        events = (ledger.state_transitions or {}).get("events", [])
        assert events[-1]["event"] == "gate_expired"
        assert events[-1]["state"] == WizardRunState.GATE_EXPIRED.value


@pytest.mark.asyncio
@pytest.mark.temporal
async def test_an_expired_gate_cannot_be_approved_afterwards(
    session_maker: async_sessionmaker[AsyncSession],
    temporal_env: WorkflowEnvironment,
) -> None:
    """`GateExpired` is terminal: a late click must not scale an abandoned run."""
    async with _worker(temporal_env, session_maker):
        orchestrator, wizard_run_id, workflow_id = await _start_run_at_the_gate(
            temporal_env, session_maker, "late click"
        )
        handle = temporal_env.client.get_workflow_handle(workflow_id)
        await temporal_env.sleep(GATE_TIMEOUT_SECONDS + 60)
        assert await handle.result() == "gate_expired"

        async with session_maker() as session:
            service = WizardService(session, orchestrator)
            with pytest.raises(InvalidStateTransitionError):
                await service.approve_run(wizard_run_id, reason="I was on holiday")


@pytest.mark.asyncio
@pytest.mark.temporal
async def test_the_workflow_records_review_routing_when_the_scaled_run_finishes(
    session_maker: async_sessionmaker[AsyncSession],
    temporal_env: WorkflowEnvironment,
) -> None:
    """The DB used to sit at `ScaledRun` forever; `ReviewRouting` was never written."""
    async with _worker(temporal_env, session_maker):
        orchestrator, wizard_run_id, workflow_id = await _start_run_at_the_gate(
            temporal_env, session_maker, "scaled completion"
        )
        async with session_maker() as session:
            service = WizardService(session, orchestrator)
            approved = await service.approve_run(wizard_run_id, reason="pilot looks right")
            # The API's optimistic write, which is all the DB used to ever get.
            assert approved.state is WizardRunState.SCALED_RUN

        handle = temporal_env.client.get_workflow_handle(workflow_id)
        assert await handle.result() == "scaled"

    async with session_maker() as session:
        run = await session.get(WizardRun, wizard_run_id)
        assert run is not None
        assert run.state is WizardRunState.REVIEW_ROUTING
        assert run.failure_reason is None


@pytest.mark.asyncio
async def test_persist_wizard_outcome_is_idempotent(session_maker) -> None:
    """Temporal retries the activity; a repeat must not append a second event."""
    async with session_maker() as session:
        project = WizardProject(name="outcome")
        session.add(project)
        await session.flush()
        run = WizardRun(wizard_project_id=project.wizard_project_id)
        session.add(run)
        await session.flush()
        session.add(
            WizardRunLedger(wizard_run_id=run.wizard_run_id, state_transitions={"events": []})
        )
        await session.commit()
        wizard_run_id = run.wizard_run_id

    acts = WizardStateActivities(session_factory=session_maker)
    for _ in range(3):
        await acts.persist_wizard_outcome(
            wizard_run_id, WizardRunState.GATE_EXPIRED.value, "expired", "gate_expired"
        )

    async with session_maker() as session:
        run = await session.get(WizardRun, wizard_run_id)
        assert run is not None
        assert run.state is WizardRunState.GATE_EXPIRED
        assert run.failure_reason == "expired"
        ledger = await session.scalar(
            select(WizardRunLedger).where(WizardRunLedger.wizard_run_id == wizard_run_id)
        )
        assert ledger is not None
        assert len(ledger.state_transitions["events"]) == 1


@pytest.mark.asyncio
async def test_persist_wizard_outcome_refuses_an_unknown_state(session_maker) -> None:
    """A typo must fail the activity, not silently store a state nothing can read."""
    acts = WizardStateActivities(session_factory=session_maker)
    with pytest.raises(ValueError):
        await acts.persist_wizard_outcome("wrn_whatever", "NotAState", None, "bogus")


# ---------------------------------------------------------------------------
# The approve/expire race (#560): exactly one side may win, and the other is told
# ---------------------------------------------------------------------------


@pytest.mark.asyncio
async def test_the_expiry_write_is_a_claim_not_an_overwrite(session_maker) -> None:
    """`persist_wizard_outcome` must refuse a state the workflow no longer owns.

    The gate timer firing and an operator clicking approve are concurrent. If the
    API records the approval first, the expiry activity must not stamp
    `GateExpired` over it — and must say it lost, so the workflow can honour the
    decision instead of discarding one a human was told had been accepted.
    """
    async with session_maker() as session:
        project = WizardProject(name="claim")
        session.add(project)
        await session.flush()
        run = WizardRun(
            wizard_project_id=project.wizard_project_id,
            state=WizardRunState.SCALED_RUN,
        )
        session.add(run)
        await session.commit()
        wizard_run_id = run.wizard_run_id

    acts = WizardStateActivities(session_factory=session_maker)
    won = await acts.persist_wizard_outcome(
        wizard_run_id,
        WizardRunState.GATE_EXPIRED.value,
        "expired",
        "gate_expired",
        [WizardRunState.HUMAN_GATE_APPROVAL.value],
    )

    assert won is False
    async with session_maker() as session:
        run = await session.get(WizardRun, wizard_run_id)
        assert run is not None
        assert run.state is WizardRunState.SCALED_RUN
        assert run.failure_reason is None


@pytest.mark.asyncio
async def test_an_approval_that_loses_the_race_is_a_conflict_not_a_false_success(
    session_maker,
) -> None:
    """The operator must not be told a decision was applied when it was discarded.

    Reproduces the interleaving exactly: `approve_run` reads the row while the gate
    is open, the signal round-trips to Temporal, and the expiry activity commits
    `GateExpired` in that window. The old code wrote `ScaledRun` over it and
    returned 200 — leaving the row non-terminal, the workflow closed
    `gate_expired`, no shards ever started, and nothing surfacing any of it.
    """
    async with session_maker() as session:
        project = WizardProject(name="race")
        session.add(project)
        await session.flush()
        run = WizardRun(
            wizard_project_id=project.wizard_project_id,
            state=WizardRunState.HUMAN_GATE_APPROVAL,
        )
        session.add(run)
        await session.flush()
        session.add(
            WizardRunLedger(wizard_run_id=run.wizard_run_id, state_transitions={"events": []})
        )
        await session.commit()
        wizard_run_id = run.wizard_run_id

    class _ExpiresDuringTheSignal(InMemoryOrchestrator):
        """The gate times out while the approve signal is in flight to Temporal.

        This is the exact window the review found: `approve_run` has already read
        the row and passed its guard, and the state write has not happened yet.
        """

        async def signal_approve(self, wizard_run, reason=None):
            # The expiry activity commits from its own connection, exactly as it
            # would from the Temporal worker. Stdlib sqlite3 keeps this out of the
            # caller's SQLAlchemy session entirely.
            connection = sqlite3.connect(_sqlite_path())
            try:
                connection.execute(
                    "UPDATE wizard_runs SET state = ?, failure_reason = ? WHERE wizard_run_id = ?",
                    (WizardRunState.GATE_EXPIRED.value, "Human gate expired.", wizard_run_id),
                )
                connection.commit()
            finally:
                connection.close()
            # Temporal accepts the signal — the workflow is open, it has simply
            # already left the `wait_condition`, so the approval is discarded.
            return await super().signal_approve(wizard_run, reason=reason)

    async with session_maker() as session:
        service = WizardService(session, _ExpiresDuringTheSignal())
        with pytest.raises(ConflictError):
            await service.approve_run(wizard_run_id, reason="I clicked in time")

    async with session_maker() as session:
        run = await session.get(WizardRun, wizard_run_id)
        assert run is not None
        assert run.state is WizardRunState.GATE_EXPIRED


@pytest.mark.asyncio
async def test_a_failed_scaled_run_records_a_reason_without_faking_a_transition(
    session_maker,
) -> None:
    """`scaled_failed` records why, and must not re-stamp the state it already had.

    Re-writing `ScaledRun` over `ScaledRun` would bump `state_entered_at` for a
    transition that never happened, corrupting the state-dwell metric the
    battle-test scenarios track.
    """
    async with session_maker() as session:
        project = WizardProject(name="scaled failure")
        session.add(project)
        await session.flush()
        run = WizardRun(
            wizard_project_id=project.wizard_project_id,
            state=WizardRunState.SCALED_RUN,
        )
        session.add(run)
        await session.commit()
        wizard_run_id, entered_at = run.wizard_run_id, run.state_entered_at

    acts = WizardStateActivities(session_factory=session_maker)
    assert await acts.persist_wizard_outcome(
        wizard_run_id, None, "Scaled run failed: boom", "scaled_failed"
    )

    async with session_maker() as session:
        run = await session.get(WizardRun, wizard_run_id)
        assert run is not None
        assert run.state is WizardRunState.SCALED_RUN
        assert run.failure_reason == "Scaled run failed: boom"
        # SQLite hands back a naive datetime; the point is that it did not move.
        assert run.state_entered_at.replace(tzinfo=None) == entered_at.replace(tzinfo=None)


# ---------------------------------------------------------------------------
# The way out of a terminal state (#560)
# ---------------------------------------------------------------------------


@pytest.mark.asyncio
async def test_an_expired_run_can_be_restarted_without_re_entering_the_project(
    session_maker,
) -> None:
    """`GateExpired` is terminal for the run, not for the project.

    Without this, every mutating endpoint guarded on a state an expired run can
    never be in, so at hour 73 the project was unusable and the scope and
    discovery plan had to be re-entered in a brand-new one. Rejection returns to
    `DiscoveryPlan` and stays recoverable; expiry must not be worse than rejection.
    """
    async with session_maker() as session:
        service = WizardService(session, InMemoryOrchestrator())
        project = await service.create_project(CreateWizardProjectRequest(name="restart"))
        await service.update_scope(project.wizard_project_id, {"domains": ["example.ch"]})
        await service.update_discovery_plan(
            project.wizard_project_id, {"seed_urls": ["https://example.ch"]}
        )
        expired = await service._get_latest_run_for_project(project.wizard_project_id)
        expired.state = WizardRunState.GATE_EXPIRED
        await session.commit()
        expired_id = expired.wizard_run_id
        project_id = project.wizard_project_id

    async with session_maker() as session:
        service = WizardService(session, InMemoryOrchestrator())
        restarted = await service.restart_run(expired_id)
        assert restarted.wizard_run_id != expired_id
        assert restarted.state is WizardRunState.DISCOVERY_PLAN

        # The project's work survived, so the operator starts a pilot, not a project.
        resumed = await service.start_pilot_run(project_id)
        assert resumed.state is WizardRunState.HUMAN_GATE_APPROVAL
        assert resumed.wizard_run_id == restarted.wizard_run_id

    async with session_maker() as session:
        # The expired run keeps its record; restarting is not a rewrite of history.
        previous = await session.get(WizardRun, expired_id)
        assert previous is not None
        assert previous.state is WizardRunState.GATE_EXPIRED


@pytest.mark.asyncio
async def test_only_a_terminally_ended_run_can_be_restarted(session_maker) -> None:
    """Restart is a recovery from a dead end, not a way to abandon a live run."""
    async with session_maker() as session:
        service = WizardService(session, InMemoryOrchestrator())
        project = await service.create_project(CreateWizardProjectRequest(name="live"))
        run = await service._get_latest_run_for_project(project.wizard_project_id)
        with pytest.raises(InvalidStateTransitionError):
            await service.restart_run(run.wizard_run_id)
