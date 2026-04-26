"""Rescore-from-correction scheduler abstraction (#427).

The corrections endpoint and service kick rescores via this Protocol so
unit tests can substitute an in-memory recorder without spinning up
Temporal. The Temporal-backed implementation idempotently starts a
`RescoreFromCorrectionWorkflow` keyed by the correction ID — re-firing
on the same correction returns the existing workflow handle.
"""

from __future__ import annotations

import logging
from dataclasses import dataclass, field
from typing import Any, Protocol

logger = logging.getLogger(__name__)


@dataclass(slots=True)
class RescoreScheduleResult:
    workflow_id: str
    workflow_run_id: str | None
    already_running: bool = False


class RescoreScheduler(Protocol):
    async def schedule(
        self,
        *,
        correction_id: str,
        target_entity_type: str,
        target_entity_id: str,
        payload: dict[str, Any],
    ) -> RescoreScheduleResult: ...


def rescore_workflow_id(correction_id: str) -> str:
    """Deterministic Temporal workflow id keyed by correction.

    Idempotency is enforced by Temporal via this id: a second `schedule`
    call for the same correction surfaces `WorkflowAlreadyStartedError`,
    which the scheduler converts to `already_running=True`.
    """

    return f"rescore-{correction_id}"


@dataclass(slots=True)
class InMemoryRescoreScheduler:
    """Test-friendly scheduler — records calls without touching Temporal."""

    triggered: list[dict[str, Any]] = field(default_factory=list)
    fail_with: Exception | None = None

    async def schedule(
        self,
        *,
        correction_id: str,
        target_entity_type: str,
        target_entity_id: str,
        payload: dict[str, Any],
    ) -> RescoreScheduleResult:
        if self.fail_with is not None:
            raise self.fail_with
        self.triggered.append(
            {
                "correction_id": correction_id,
                "target_entity_type": target_entity_type,
                "target_entity_id": target_entity_id,
                "payload": payload,
            }
        )
        return RescoreScheduleResult(
            workflow_id=rescore_workflow_id(correction_id),
            workflow_run_id=f"run-{correction_id}",
            already_running=False,
        )


class TemporalRescoreScheduler:
    """Production scheduler — kicks the rescore workflow on Temporal.

    Uses the same connect-on-demand pattern as the wizard orchestrator
    in `platform_control.services.orchestrator`.
    """

    def __init__(
        self,
        namespace: str,
        task_queue: str,
        *,
        target: str = "localhost:7233",
        client: Any | None = None,
    ) -> None:
        self.namespace = namespace
        self.task_queue = task_queue
        self.target = target
        self._injected_client = client
        self._connected_client: Any | None = None

    async def _get_client(self) -> Any:
        if self._injected_client is not None:
            return self._injected_client
        if self._connected_client is None:
            from platform_control.config import get_settings
            from platform_control.temporal.client import connect_temporal

            self._connected_client = await connect_temporal(
                get_settings(),
                target=self.target,
                namespace=self.namespace,
            )
        return self._connected_client

    async def schedule(
        self,
        *,
        correction_id: str,
        target_entity_type: str,
        target_entity_id: str,
        payload: dict[str, Any],
    ) -> RescoreScheduleResult:
        from temporalio.exceptions import WorkflowAlreadyStartedError

        from platform_control.temporal.workflows import (
            RescoreFromCorrectionInput,
            RescoreFromCorrectionWorkflow,
        )

        client = await self._get_client()
        workflow_id = rescore_workflow_id(correction_id)
        try:
            handle = await client.start_workflow(
                RescoreFromCorrectionWorkflow.run,
                RescoreFromCorrectionInput(
                    correction_id=correction_id,
                    target_entity_type=target_entity_type,
                    target_entity_id=target_entity_id,
                    payload=payload,
                ),
                id=workflow_id,
                task_queue=self.task_queue,
            )
            return RescoreScheduleResult(
                workflow_id=workflow_id,
                workflow_run_id=getattr(handle, "result_run_id", None),
                already_running=False,
            )
        except WorkflowAlreadyStartedError:
            logger.info(
                "rescore_workflow_already_running",
                extra={"correction_id": correction_id, "workflow_id": workflow_id},
            )
            return RescoreScheduleResult(
                workflow_id=workflow_id,
                workflow_run_id=None,
                already_running=True,
            )
