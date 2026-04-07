from __future__ import annotations

from datetime import UTC, datetime
from typing import TYPE_CHECKING, Literal

from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from platform_control.domain import ReviewTaskStatus, WizardProjectStatus, WizardRunState
from platform_control.errors import ConflictError, InvalidStateTransitionError, NotFoundError
from platform_control.models.review_task import ReviewTask
from platform_control.models.wizard_project import WizardProject
from platform_control.models.wizard_run import WizardRun
from platform_control.models.wizard_run_ledger import WizardRunLedger
from platform_control.schemas.wizard import (
    ArgillaReviewSyncRequest,
    ArgillaReviewSyncResponse,
    CreateReviewTaskRequest,
    CreateReviewTaskResponse,
    CreateWizardProjectRequest,
)
from platform_control.services.orchestrator import Orchestrator

if TYPE_CHECKING:
    from platform_control.services.argilla_enqueue_service import ArgillaEnqueueService


class WizardService:
    def __init__(
        self,
        session: AsyncSession,
        orchestrator: Orchestrator,
        *,
        argilla_enqueue: ArgillaEnqueueService | None = None,
    ) -> None:
        self.session = session
        self.orchestrator = orchestrator
        self._argilla_enqueue = argilla_enqueue

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

    async def create_review_task(
        self, request: CreateReviewTaskRequest
    ) -> CreateReviewTaskResponse:
        await self.get_run(request.wizard_run_id)
        existing = await self.session.scalar(
            select(ReviewTask).where(ReviewTask.argilla_external_id == request.argilla_external_id)
        )
        if existing is not None:
            raise ConflictError(
                f"Review task already exists for Argilla external_id: {request.argilla_external_id}"
            )

        task = ReviewTask(
            wizard_run_id=request.wizard_run_id,
            argilla_external_id=request.argilla_external_id,
            record_id=request.record_id,
            payload=dict(request.payload),
        )
        self.session.add(task)
        await self.session.flush()

        payload_for_argilla = dict(task.payload)
        meta = dict(payload_for_argilla.get("metadata") or {})
        meta.setdefault("wizard_run_id", task.wizard_run_id)
        meta.setdefault("review_task_id", task.review_task_id)
        if task.record_id:
            meta.setdefault("recordId", task.record_id)
        payload_for_argilla["metadata"] = meta

        enqueue_outcome: Literal["enqueued", "skipped_not_configured", "failed"]
        enqueue_detail: str | None = None

        if self._argilla_enqueue is None:
            enqueue_outcome = "skipped_not_configured"
            enqueue_detail = "Argilla enqueue service not wired for this call site"
            await self._bump_ledger_enqueue(task.wizard_run_id, "skipped")
        else:
            result = await self._argilla_enqueue.enqueue_record(
                external_id=task.argilla_external_id,
                task_payload=payload_for_argilla,
                idempotency_key=task.review_task_id,
            )
            enqueue_detail = result.detail
            if result.outcome == "enqueued":
                task.argilla_enqueued_at = datetime.now(UTC)
                task.argilla_enqueue_last_error = None
                enqueue_outcome = "enqueued"
                await self._bump_ledger_enqueue(task.wizard_run_id, "succeeded")
            elif result.outcome == "skipped_not_configured":
                enqueue_outcome = "skipped_not_configured"
                await self._bump_ledger_enqueue(task.wizard_run_id, "skipped")
            else:
                task.argilla_enqueue_last_error = (result.detail or "unknown")[:2000]
                enqueue_outcome = "failed"
                await self._bump_ledger_enqueue(task.wizard_run_id, "failed")

        await self.session.commit()
        await self.session.refresh(task)
        return CreateReviewTaskResponse(
            review_task_id=task.review_task_id,
            wizard_run_id=task.wizard_run_id,
            argilla_external_id=task.argilla_external_id,
            record_id=task.record_id,
            status=task.status,
            payload=task.payload,
            decision_payload=task.decision_payload,
            processed_at=task.processed_at,
            argilla_enqueued_at=task.argilla_enqueued_at,
            argilla_enqueue_last_error=task.argilla_enqueue_last_error,
            created_at=task.created_at,
            updated_at=task.updated_at,
            enqueue_outcome=enqueue_outcome,
            enqueue_detail=enqueue_detail,
        )

    async def _bump_ledger_enqueue(
        self, wizard_run_id: str, bucket: Literal["succeeded", "skipped", "failed"]
    ) -> None:
        ledger = await self.session.scalar(
            select(WizardRunLedger).where(WizardRunLedger.wizard_run_id == wizard_run_id)
        )
        if ledger is None:
            return
        summary = dict(ledger.error_summary or {})
        key = {
            "succeeded": "argilla_enqueue_succeeded",
            "skipped": "argilla_enqueue_skipped",
            "failed": "argilla_enqueue_failed",
        }[bucket]
        summary[key] = int(summary.get(key, 0)) + 1
        ledger.error_summary = summary

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
        wizard_run.progress = {
            **dict(wizard_run.progress or {}),
            "sample_limit": sample_limit or 0,
        }
        await self._append_transition(wizard_run, "pilot_started")
        await self.session.commit()
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

    async def sync_reviews_from_argilla(
        self, payload: ArgillaReviewSyncRequest
    ) -> ArgillaReviewSyncResponse:
        accepted = 0
        duplicates = 0
        failed = 0
        for incoming in payload.tasks:
            task = await self.session.scalar(
                select(ReviewTask).where(ReviewTask.argilla_external_id == incoming.external_id)
            )
            if task is None:
                failed += 1
                continue

            previous_decision = dict(task.decision_payload or {})
            previous_ts = previous_decision.get("annotation_updated_at")
            if previous_ts and str(previous_ts) >= incoming.annotation_updated_at.isoformat():
                duplicates += 1
                continue

            task.status = ReviewTaskStatus.COMPLETED
            task.processed_at = datetime.now(UTC)
            task.decision_payload = incoming.model_dump(mode="json")
            accepted += 1

            ledger = await self.session.scalar(
                select(WizardRunLedger).where(WizardRunLedger.wizard_run_id == task.wizard_run_id)
            )
            if ledger is not None:
                summary = dict(ledger.error_summary or {})
                summary["review_sync_accepted"] = int(summary.get("review_sync_accepted", 0)) + 1
                ledger.error_summary = summary

        await self.session.commit()
        return ArgillaReviewSyncResponse(
            accepted=accepted,
            duplicates=duplicates,
            failed=failed,
        )

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
