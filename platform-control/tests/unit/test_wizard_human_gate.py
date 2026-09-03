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

import pytest
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession, async_sessionmaker
from temporalio.testing import WorkflowEnvironment
from temporalio.worker import Worker

from platform_control.domain import WizardRunState
from platform_control.errors import InvalidStateTransitionError
from platform_control.models.wizard_project import WizardProject
from platform_control.models.wizard_run import WizardRun
from platform_control.models.wizard_run_ledger import WizardRunLedger
from platform_control.schemas.wizard import CreateWizardProjectRequest
from platform_control.services.orchestrator import TemporalOrchestrator
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
