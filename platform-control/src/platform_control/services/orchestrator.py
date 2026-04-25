from __future__ import annotations

from dataclasses import dataclass
from datetime import UTC, datetime
from typing import Protocol

from temporalio.client import Client
from temporalio.exceptions import TemporalError, WorkflowAlreadyStartedError

from platform_control.domain import WizardRunState
from platform_control.errors import InvalidStateTransitionError, OrchestrationError
from platform_control.models.wizard_run import WizardRun
from platform_control.temporal.workflows import (
    RescoreCorrectionWorkflow,
    ReviewDrainWorkflow,
    ScopeShardWorkflow,
    WizardRunWorkflow,
)


def wizard_run_workflow_id(wizard_run_id: str) -> str:
    """Deterministic Temporal workflow id for a wizard run (matches DB `workflow_id`)."""
    return f"wizard-run-{wizard_run_id}"


def _sanitize_workflow_id_segment(segment: str) -> str:
    return "".join(c if c.isalnum() or c in "-_" else "_" for c in segment)[:200] or "default"


@dataclass(slots=True)
class OrchestrationResult:
    workflow_id: str | None = None
    next_state: WizardRunState | None = None
    state_entered_at: datetime | None = None


class Orchestrator(Protocol):
    async def start_pilot_run(self, wizard_run: WizardRun) -> OrchestrationResult: ...

    async def signal_approve(
        self, wizard_run: WizardRun, reason: str | None = None
    ) -> OrchestrationResult: ...

    async def signal_reject(
        self, wizard_run: WizardRun, reason: str | None = None
    ) -> OrchestrationResult: ...


class InMemoryOrchestrator:
    async def start_rescore_workflow(
        self,
        *,
        rescore_correction_id: str,
        source_correction_id: str,
        target_entity_type: str,
        target_entity_id: str,
        dry_run: bool,
    ) -> tuple[str, str | None]:
        """Synchronous-style stub used in dev / unit tests.

        Returns a deterministic in-memory workflow id and ``None`` for the
        Temporal run id. The corrections router relies on this stub so
        ``request_rescore`` can be exercised without a Temporal cluster.
        """
        del rescore_correction_id, target_entity_type, dry_run
        from platform_control.services.correction_service import rescore_workflow_id

        return rescore_workflow_id(source_correction_id, target_entity_id), None

    async def start_pilot_run(self, wizard_run: WizardRun) -> OrchestrationResult:
        if wizard_run.state is not WizardRunState.DISCOVERY_PLAN:
            raise InvalidStateTransitionError(
                f"Cannot start pilot run from state {wizard_run.state}."
            )
        now = datetime.now(UTC)
        # In-memory mode simulates a completed pilot and lands at approval gate.
        return OrchestrationResult(
            workflow_id=f"in_memory_{wizard_run.wizard_run_id}",
            next_state=WizardRunState.HUMAN_GATE_APPROVAL,
            state_entered_at=now,
        )

    async def signal_approve(
        self, wizard_run: WizardRun, reason: str | None = None
    ) -> OrchestrationResult:
        del reason
        if wizard_run.state is not WizardRunState.HUMAN_GATE_APPROVAL:
            raise InvalidStateTransitionError(f"Cannot approve state {wizard_run.state}.")
        return OrchestrationResult(
            next_state=WizardRunState.SCALED_RUN,
            state_entered_at=datetime.now(UTC),
        )

    async def signal_reject(
        self, wizard_run: WizardRun, reason: str | None = None
    ) -> OrchestrationResult:
        if wizard_run.state is not WizardRunState.HUMAN_GATE_APPROVAL:
            raise InvalidStateTransitionError(f"Cannot reject state {wizard_run.state}.")
        if not reason:
            raise InvalidStateTransitionError("Rejection reason is required.")
        return OrchestrationResult(
            next_state=WizardRunState.DISCOVERY_PLAN,
            state_entered_at=datetime.now(UTC),
        )


class TemporalOrchestrator:
    """Temporal-backed wizard orchestration: start workflow + human-gate signals."""

    def __init__(
        self,
        namespace: str,
        task_queue: str,
        *,
        target: str = "localhost:7233",
        client: Client | None = None,
    ) -> None:
        self.namespace = namespace
        self.task_queue = task_queue
        self.target = target
        self._injected_client = client
        self._connected_client: Client | None = None

    async def _get_client(self) -> Client:
        if self._injected_client is not None:
            return self._injected_client
        if self._connected_client is None:
            try:
                self._connected_client = await Client.connect(
                    self.target,
                    namespace=self.namespace,
                )
            except Exception as exc:  # noqa: BLE001 — surface as domain error
                raise OrchestrationError(
                    f"Cannot connect to Temporal at {self.target} (namespace={self.namespace})."
                ) from exc
        return self._connected_client

    async def start_pilot_run(self, wizard_run: WizardRun) -> OrchestrationResult:
        if wizard_run.state is not WizardRunState.DISCOVERY_PLAN:
            raise InvalidStateTransitionError(
                f"Cannot start pilot run from state {wizard_run.state}."
            )
        now = datetime.now(UTC)
        workflow_id = wizard_run_workflow_id(wizard_run.wizard_run_id)
        client = await self._get_client()
        try:
            await client.start_workflow(
                WizardRunWorkflow.run,
                wizard_run.wizard_run_id,
                id=workflow_id,
                task_queue=self.task_queue,
            )
        except WorkflowAlreadyStartedError:
            pass
        except TemporalError as exc:
            raise OrchestrationError(f"Temporal start_workflow failed: {exc}") from exc
        return OrchestrationResult(
            workflow_id=workflow_id,
            next_state=WizardRunState.PILOT_RUN,
            state_entered_at=now,
        )

    def _gate_states(self) -> tuple[WizardRunState, ...]:
        """States from which the API may signal the human gate on the workflow.

        Only ``HUMAN_GATE_APPROVAL`` is valid: the ``persist_pilot_completed`` Temporal
        activity (wired in ``WizardRunWorkflow``) updates the DB to this state before the
        workflow blocks on the operator signal, so the approve/reject endpoints can guard
        correctly without the workaround of accepting ``PILOT_RUN`` here.
        """
        return (WizardRunState.HUMAN_GATE_APPROVAL,)

    async def signal_approve(
        self, wizard_run: WizardRun, reason: str | None = None
    ) -> OrchestrationResult:
        if wizard_run.state not in self._gate_states():
            raise InvalidStateTransitionError(f"Cannot approve state {wizard_run.state}.")
        workflow_id = wizard_run.workflow_id or wizard_run_workflow_id(wizard_run.wizard_run_id)
        client = await self._get_client()
        handle = client.get_workflow_handle(workflow_id)
        try:
            await handle.signal(WizardRunWorkflow.approve, reason)
        except TemporalError as exc:
            raise OrchestrationError(f"Temporal approve signal failed: {exc}") from exc
        return OrchestrationResult(
            next_state=WizardRunState.SCALED_RUN,
            state_entered_at=datetime.now(UTC),
        )

    async def signal_reject(
        self, wizard_run: WizardRun, reason: str | None = None
    ) -> OrchestrationResult:
        if wizard_run.state not in self._gate_states():
            raise InvalidStateTransitionError(f"Cannot reject state {wizard_run.state}.")
        if not reason:
            raise InvalidStateTransitionError("Rejection reason is required.")
        workflow_id = wizard_run.workflow_id or wizard_run_workflow_id(wizard_run.wizard_run_id)
        client = await self._get_client()
        handle = client.get_workflow_handle(workflow_id)
        try:
            await handle.signal(WizardRunWorkflow.reject, reason)
        except TemporalError as exc:
            raise OrchestrationError(f"Temporal reject signal failed: {exc}") from exc
        return OrchestrationResult(
            next_state=WizardRunState.DISCOVERY_PLAN,
            state_entered_at=datetime.now(UTC),
        )

    async def start_scope_shard_workflow(
        self,
        wizard_run_id: str,
        *,
        scope_shard_key: str = "default",
        resume_token: str | None = None,
    ) -> str:
        """Start a scope-shard workflow via API (separate id from parent-spawned children)."""
        safe_key = _sanitize_workflow_id_segment(scope_shard_key)
        child_id = f"{wizard_run_workflow_id(wizard_run_id)}__scope_shard_api_{safe_key}"
        client = await self._get_client()
        try:
            await client.start_workflow(
                ScopeShardWorkflow.run,
                args=[wizard_run_id, scope_shard_key, resume_token],
                id=child_id,
                task_queue=self.task_queue,
            )
        except WorkflowAlreadyStartedError:
            pass
        except TemporalError as exc:
            raise OrchestrationError(f"Temporal start ScopeShardWorkflow failed: {exc}") from exc
        return child_id

    async def start_review_drain_workflow(self, wizard_run_id: str) -> str:
        """Start review-drain via API (id suffix `review_drain_api`, not parent child id)."""
        child_id = f"{wizard_run_workflow_id(wizard_run_id)}__review_drain_api"
        client = await self._get_client()
        try:
            await client.start_workflow(
                ReviewDrainWorkflow.run,
                args=[wizard_run_id],
                id=child_id,
                task_queue=self.task_queue,
            )
        except WorkflowAlreadyStartedError:
            pass
        except TemporalError as exc:
            raise OrchestrationError(f"Temporal start ReviewDrainWorkflow failed: {exc}") from exc
        return child_id

    async def start_rescore_workflow(
        self,
        *,
        rescore_correction_id: str,
        source_correction_id: str,
        target_entity_type: str,
        target_entity_id: str,
        dry_run: bool,
    ) -> tuple[str, str | None]:
        """Start ``RescoreCorrectionWorkflow`` for a rescore-request correction.

        The workflow id is derived from ``(source_correction_id,
        target_entity_id)`` so repeated calls collide on Temporal's
        ``WorkflowAlreadyStartedError`` rather than spawning duplicate
        executions.
        """
        del target_entity_type, dry_run  # carried on the row + payload
        from platform_control.services.correction_service import rescore_workflow_id

        workflow_id = rescore_workflow_id(source_correction_id, target_entity_id)
        client = await self._get_client()
        try:
            handle = await client.start_workflow(
                RescoreCorrectionWorkflow.run,
                rescore_correction_id,
                id=workflow_id,
                task_queue=self.task_queue,
            )
        except WorkflowAlreadyStartedError:
            handle = client.get_workflow_handle(workflow_id)
        except TemporalError as exc:
            raise OrchestrationError(
                f"Temporal start RescoreCorrectionWorkflow failed: {exc}"
            ) from exc
        run_id = getattr(handle, "first_execution_run_id", None) or getattr(handle, "run_id", None)
        return workflow_id, run_id
