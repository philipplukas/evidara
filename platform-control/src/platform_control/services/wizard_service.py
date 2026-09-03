from __future__ import annotations

from datetime import UTC, datetime

from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from platform_control.domain import ReviewTaskStatus, WizardProjectStatus, WizardRunState
from platform_control.errors import ConflictError, InvalidStateTransitionError, NotFoundError
from platform_control.models.review_task import ReviewTask
from platform_control.models.wizard_project import WizardProject
from platform_control.models.wizard_run import WizardRun
from platform_control.models.wizard_run_ledger import WizardRunLedger
from platform_control.schemas.wizard import (
    CreateReviewTaskRequest,
    CreateWizardProjectRequest,
    ReviewDecisionRequest,
    ReviewTaskResponse,
)
from platform_control.services.orchestrator import Orchestrator
from platform_control.services.wizard_progress import update_wizard_progress_in_session


class WizardService:
    def __init__(self, session: AsyncSession, orchestrator: Orchestrator) -> None:
        self.session = session
        self.orchestrator = orchestrator

    async def create_project(self, request: CreateWizardProjectRequest) -> WizardProject:
        project = WizardProject(name=request.name, status=WizardProjectStatus.DRAFT)
        self.session.add(project)
        await self.session.flush()

        wizard_run = WizardRun(
            wizard_project_id=project.wizard_project_id,
            state=WizardRunState.DRAFT_SCOPE,
            progress={},
            quality={},
            health={},
        )
        self.session.add(wizard_run)
        await self.session.flush()

        self.session.add(
            WizardRunLedger(
                wizard_run_id=wizard_run.wizard_run_id,
                state_transitions={
                    "events": [
                        {
                            "state": WizardRunState.DRAFT_SCOPE.value,
                            "entered_at": wizard_run.state_entered_at.isoformat(),
                            "event": "created",
                        }
                    ]
                },
                retry_counters={},
                error_summary={},
                sla_markers={},
            )
        )
        await self.session.commit()
        await self.session.refresh(project)
        return project

    async def get_project(self, wizard_project_id: str) -> WizardProject:
        project = await self.session.get(WizardProject, wizard_project_id)
        if project is None:
            raise NotFoundError(f"Wizard project not found: {wizard_project_id}")
        return project

    async def get_run(self, wizard_run_id: str) -> WizardRun:
        wizard_run = await self.session.get(WizardRun, wizard_run_id)
        if wizard_run is None:
            raise NotFoundError(f"Wizard run not found: {wizard_run_id}")
        return wizard_run

    async def get_review_task(self, review_task_id: str) -> ReviewTask:
        task = await self.session.get(ReviewTask, review_task_id)
        if task is None:
            raise NotFoundError(f"Review task not found: {review_task_id}")
        return task

    async def create_review_task(self, request: CreateReviewTaskRequest) -> ReviewTaskResponse:
        """Route one extraction into the operator review queue.

        Persisting the task *is* the enqueue: the queue is the ``review_tasks``
        table, read by the admin app. There is no outbound push to a review tool
        (ADR-0031).
        """
        await self.get_run(request.wizard_run_id)
        existing = await self.session.scalar(
            select(ReviewTask).where(ReviewTask.external_id == request.external_id)
        )
        if existing is not None:
            raise ConflictError(
                f"Review task already exists for external_id: {request.external_id}"
            )

        task = ReviewTask(
            wizard_run_id=request.wizard_run_id,
            external_id=request.external_id,
            record_id=request.record_id,
            payload=dict(request.payload),
        )
        self.session.add(task)
        await self.session.commit()
        await self.session.refresh(task)
        return ReviewTaskResponse.model_validate(task)

    async def update_scope(self, wizard_project_id: str, scope: dict) -> WizardProject:
        project = await self.get_project(wizard_project_id)
        wizard_run = await self._get_latest_run_for_project(wizard_project_id)
        if wizard_run.state is not WizardRunState.DRAFT_SCOPE:
            raise InvalidStateTransitionError(f"Cannot update scope in state {wizard_run.state}.")
        if not scope:
            raise InvalidStateTransitionError("Scope cannot be empty.")

        project.scope = scope
        project.status = WizardProjectStatus.ACTIVE
        wizard_run.state = WizardRunState.DISCOVERY_PLAN
        wizard_run.state_entered_at = datetime.now(UTC)
        await self._append_transition(wizard_run, "scope_submitted")
        await self.session.commit()
        await self.session.refresh(project)
        return project

    async def update_discovery_plan(
        self, wizard_project_id: str, discovery_plan: dict
    ) -> WizardProject:
        project = await self.get_project(wizard_project_id)
        wizard_run = await self._get_latest_run_for_project(wizard_project_id)
        if wizard_run.state is not WizardRunState.DISCOVERY_PLAN:
            raise InvalidStateTransitionError(
                f"Cannot update discovery plan in state {wizard_run.state}."
            )
        if not discovery_plan:
            raise InvalidStateTransitionError("Discovery plan cannot be empty.")

        project.discovery_plan = discovery_plan
        await self.session.commit()
        await self.session.refresh(project)
        return project

    async def start_pilot_run(
        self, wizard_project_id: str, sample_limit: int | None = None
    ) -> WizardRun:
        project = await self.get_project(wizard_project_id)
        del project
        wizard_run = await self._get_latest_run_for_project(wizard_project_id)
        if wizard_run.state is not WizardRunState.DISCOVERY_PLAN:
            raise InvalidStateTransitionError(
                f"Cannot start pilot run in state {wizard_run.state}."
            )
        result = await self.orchestrator.start_pilot_run(wizard_run)
        wizard_run.workflow_id = result.workflow_id or wizard_run.workflow_id
        wizard_run.state = result.next_state or WizardRunState.PILOT_RUN
        wizard_run.state_entered_at = result.state_entered_at or datetime.now(UTC)
        await self._append_transition(wizard_run, "pilot_started")
        await self.session.commit()

        # `progress` is a compare-and-set column (#561): every writer must go
        # through `update_wizard_progress`, or it clobbers whatever a shard
        # activity committed *and* leaves `progress_version` unchanged, so no CAS
        # writer can even detect the loss. This used to be a plain assignment from
        # a snapshot read before `orchestrator.start_pilot_run` returned, which is
        # exactly the unguarded read-modify-write the column exists to prevent.
        # Written after the commit above so it is its own short transaction rather
        # than a second uncommitted writer holding the row.
        await update_wizard_progress_in_session(
            self.session,
            wizard_run.wizard_run_id,
            lambda progress: {**progress, "sample_limit": sample_limit or 0},
        )
        await self.session.refresh(wizard_run)
        return wizard_run

    async def approve_run(self, wizard_run_id: str, reason: str | None = None) -> WizardRun:
        wizard_run = await self.get_run(wizard_run_id)
        result = await self.orchestrator.signal_approve(wizard_run, reason=reason)
        wizard_run.state = result.next_state or wizard_run.state
        wizard_run.state_entered_at = result.state_entered_at or datetime.now(UTC)
        await self._append_transition(wizard_run, "gate_approved", reason=reason)
        await self.session.commit()
        await self.session.refresh(wizard_run)
        return wizard_run

    async def reject_run(self, wizard_run_id: str, reason: str | None = None) -> WizardRun:
        wizard_run = await self.get_run(wizard_run_id)
        result = await self.orchestrator.signal_reject(wizard_run, reason=reason)
        wizard_run.state = result.next_state or wizard_run.state
        wizard_run.state_entered_at = result.state_entered_at or datetime.now(UTC)
        await self._append_transition(wizard_run, "gate_rejected", reason=reason)
        await self.session.commit()
        await self.session.refresh(wizard_run)
        return wizard_run

    async def record_review_decision(
        self,
        review_task_id: str,
        request: ReviewDecisionRequest,
        *,
        reviewed_by: str,
    ) -> ReviewTaskResponse:
        """Record an operator's verdict, moving the task to a terminal state.

        Replaces the ``sync-from-argilla`` batch poll-back (ADR-0031). A decision is
        now pushed for one task by whoever reviewed it, so there is no external
        annotation store to reconcile with and no last-writer-wins timestamp to
        compare: a task that already carries a decision conflicts rather than being
        silently overwritten.

        ``reviewed_by`` is supplied by the caller *route* from the authenticated
        principal and always overwrites whatever the request body carried. The schema
        field is retained (removing it is a contract change) but is now inert.
        """
        task = await self.get_review_task(review_task_id)
        if task.status is not ReviewTaskStatus.PENDING:
            raise ConflictError(f"Review task {review_task_id} is already {task.status.value}.")

        task.status = ReviewTaskStatus.COMPLETED
        task.processed_at = datetime.now(UTC)
        task.decision_payload = {
            **request.model_dump(mode="json"),
            # Authenticated principal wins over anything the client sent.
            "reviewed_by": reviewed_by,
            "recorded_at": task.processed_at.isoformat(),
        }

        ledger = await self.session.scalar(
            select(WizardRunLedger).where(WizardRunLedger.wizard_run_id == task.wizard_run_id)
        )
        if ledger is not None:
            summary = dict(ledger.error_summary or {})
            summary["review_decisions_recorded"] = (
                int(summary.get("review_decisions_recorded", 0)) + 1
            )
            ledger.error_summary = summary

        await self.session.commit()
        await self.session.refresh(task)
        return ReviewTaskResponse.model_validate(task)

    async def _get_latest_run_for_project(self, wizard_project_id: str) -> WizardRun:
        wizard_run = await self.session.scalar(
            select(WizardRun)
            .where(WizardRun.wizard_project_id == wizard_project_id)
            .order_by(WizardRun.created_at.desc())
            .limit(1)
        )
        if wizard_run is None:
            raise NotFoundError(f"No wizard run found for project: {wizard_project_id}")
        return wizard_run

    async def _append_transition(
        self, wizard_run: WizardRun, event: str, reason: str | None = None
    ) -> None:
        ledger = await self.session.scalar(
            select(WizardRunLedger).where(WizardRunLedger.wizard_run_id == wizard_run.wizard_run_id)
        )
        if ledger is None:
            return
        transitions = dict(ledger.state_transitions or {})
        events = list(transitions.get("events", []))
        event_payload = {
            "state": wizard_run.state.value,
            "entered_at": wizard_run.state_entered_at.isoformat(),
            "event": event,
        }
        if reason:
            event_payload["reason"] = reason
        events.append(event_payload)
        transitions["events"] = events
        ledger.state_transitions = transitions
