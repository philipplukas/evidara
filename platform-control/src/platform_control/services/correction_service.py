"""Correction service — read/queue + rescore-loop orchestration.

This module covers two surfaces against the :class:`Correction` audit log:

* The operator read surface used by the queue endpoint and the per-entity
  history endpoint owned by #421. Most operator-correction writes happen
  inside other services (e.g. ``CommentaryInsightService`` writes a
  ``field_edit`` row when a patch is applied).
* The rescore-request loop owned by #427: ``request_rescore`` schedules a
  Temporal workflow on top of a parent correction, and ``record_outcome`` is
  the workflow callback that persists the terminal outcome.
"""

from __future__ import annotations

import logging
from datetime import UTC, datetime
from typing import Protocol

from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from platform_control.domain import (
    CorrectionStatus,
    CorrectionTargetEntityType,
    CorrectionType,
)
from platform_control.errors import NotFoundError
from platform_control.models.correction import Correction
from platform_control.observability.event_logging import log_event
from platform_control.schemas.correction import RescoreRequest, RescoreResponse

LOGGER = logging.getLogger("platform_control.correction_service")


def rescore_workflow_id(source_correction_id: str, target_entity_id: str) -> str:
    """Deterministic Temporal workflow id for a (source_correction, target) pair.

    Idempotent calls to ``request_rescore`` share this id so Temporal's
    ``WorkflowAlreadyStartedError`` short-circuit is enough to make repeated
    POSTs safe — the row in the corrections table also acts as an
    application-level guard.
    """
    safe_target = "".join(c if c.isalnum() or c in "-_" else "_" for c in target_entity_id)[:100]
    return f"rescore-{source_correction_id}-{safe_target}"


class RescoreOrchestrator(Protocol):
    """Minimal Temporal-orchestrator surface used by the rescore loop."""

    async def start_rescore_workflow(
        self,
        *,
        rescore_correction_id: str,
        source_correction_id: str,
        target_entity_type: str,
        target_entity_id: str,
        dry_run: bool,
    ) -> tuple[str, str | None]:
        """Start (or attach to) the rescore workflow.

        Returns ``(workflow_id, run_id)``. ``run_id`` is Temporal's
        per-execution id and may be ``None`` for in-memory orchestrators.
        """


class CorrectionService:
    def __init__(
        self,
        session: AsyncSession,
        *,
        rescore_orchestrator: RescoreOrchestrator | None = None,
    ) -> None:
        self.session = session
        self._rescore_orchestrator = rescore_orchestrator

    async def get(self, correction_id: str) -> Correction:
        row = await self.session.get(Correction, correction_id)
        if row is None:
            raise NotFoundError(f"Correction not found: {correction_id}")
        return row

    # Alias used by the rescore code path.
    async def get_correction(self, correction_id: str) -> Correction:
        return await self.get(correction_id)

    async def list_queue(
        self,
        *,
        target_entity_type: CorrectionTargetEntityType | None = None,
        correction_type: CorrectionType | None = None,
        status: CorrectionStatus = CorrectionStatus.PENDING,
        limit: int = 50,
    ) -> list[Correction]:
        """Return the operator queue, ordered by oldest-first.

        Pending corrections are surfaced oldest first so the queue drains
        FIFO; that's the boring-but-correct ordering for an action queue.
        Other status filters keep the same ordering for predictability.
        """
        stmt = select(Correction).where(Correction.status == status)
        if target_entity_type is not None:
            stmt = stmt.where(Correction.target_entity_type == target_entity_type)
        if correction_type is not None:
            stmt = stmt.where(Correction.correction_type == correction_type)
        stmt = stmt.order_by(Correction.created_at.asc()).limit(limit)
        result = await self.session.scalars(stmt)
        return list(result)

    async def list_history_for_entity(
        self,
        *,
        target_entity_type: CorrectionTargetEntityType,
        target_entity_id: str,
        limit: int = 200,
    ) -> list[Correction]:
        """All corrections for a single entity, newest first."""
        stmt = (
            select(Correction)
            .where(
                Correction.target_entity_type == target_entity_type,
                Correction.target_entity_id == target_entity_id,
            )
            .order_by(Correction.created_at.desc())
            .limit(limit)
        )
        result = await self.session.scalars(stmt)
        return list(result)

    # ------------------------------------------------------------------ #
    # Rescore loop (#427)
    # ------------------------------------------------------------------ #

    async def find_existing_rescore(
        self,
        *,
        source_correction_id: str,
        target_entity_id: str,
    ) -> Correction | None:
        return await self.session.scalar(
            select(Correction).where(
                Correction.correction_type == CorrectionType.RESCORE_REQUEST,
                Correction.source_correction_id == source_correction_id,
                Correction.target_entity_id == target_entity_id,
            )
        )

    async def request_rescore(
        self,
        source_correction_id: str,
        request: RescoreRequest,
    ) -> RescoreResponse:
        """Schedule a targeted rescore for ``source_correction_id``.

        Idempotent on ``(source_correction_id, target_entity_id)`` — repeated
        calls return the existing rescore row + workflow ids without
        scheduling a second workflow and without writing a new audit row.
        """
        source = await self.get_correction(source_correction_id)
        target_entity_type = source.target_entity_type
        target_entity_id = source.target_entity_id

        existing = await self.find_existing_rescore(
            source_correction_id=source_correction_id,
            target_entity_id=target_entity_id,
        )
        if existing is not None:
            log_event(
                LOGGER,
                logging.INFO,
                "correction.rescore.idempotent_replay",
                event_type="correction.rescore",
                status="triggered",
                source_correction_id=source_correction_id,
                target_entity_type=str(target_entity_type),
                target_entity_id=target_entity_id,
                rescore_correction_id=existing.correction_id,
                workflow_id=existing.workflow_id,
            )
            return RescoreResponse(
                rescore_correction_id=existing.correction_id,
                workflow_id=existing.workflow_id
                or rescore_workflow_id(source_correction_id, target_entity_id),
                run_id=existing.workflow_run_id,
            )

        rescore = Correction(
            correction_type=CorrectionType.RESCORE_REQUEST,
            status=CorrectionStatus.PENDING,
            target_entity_type=target_entity_type,
            target_entity_id=target_entity_id,
            source_correction_id=source_correction_id,
            rationale=request.rationale,
            payload={
                "source_correction_id": source_correction_id,
                "dry_run": request.dry_run,
                "outcome_log": [],
            },
        )
        self.session.add(rescore)
        await self.session.flush()

        workflow_id: str | None = None
        run_id: str | None = None
        if self._rescore_orchestrator is not None:
            workflow_id, run_id = await self._rescore_orchestrator.start_rescore_workflow(
                rescore_correction_id=rescore.correction_id,
                source_correction_id=source_correction_id,
                target_entity_type=str(target_entity_type),
                target_entity_id=target_entity_id,
                dry_run=request.dry_run,
            )
        else:
            workflow_id = rescore_workflow_id(source_correction_id, target_entity_id)

        rescore.workflow_id = workflow_id
        rescore.workflow_run_id = run_id
        rescore.status = CorrectionStatus.TRIGGERED
        await self.session.commit()
        await self.session.refresh(rescore)

        log_event(
            LOGGER,
            logging.INFO,
            "correction.rescore.triggered",
            event_type="correction.rescore",
            status="triggered",
            source_correction_id=source_correction_id,
            target_entity_type=str(target_entity_type),
            target_entity_id=target_entity_id,
            rescore_correction_id=rescore.correction_id,
            workflow_id=workflow_id,
            workflow_run_id=run_id,
            dry_run=request.dry_run,
        )

        return RescoreResponse(
            rescore_correction_id=rescore.correction_id,
            workflow_id=workflow_id or "",
            run_id=run_id,
        )

    async def record_outcome(
        self,
        rescore_correction_id: str,
        *,
        outcome: CorrectionStatus,
        resulting_run_id: str | None = None,
        resulting_extraction_id: str | None = None,
        diff: dict | None = None,
        error: str | None = None,
    ) -> Correction:
        """Persist the rescore-workflow's terminal outcome onto the rescore row."""
        rescore = await self.get_correction(rescore_correction_id)
        if rescore.correction_type is not CorrectionType.RESCORE_REQUEST:
            raise NotFoundError(f"Correction is not a rescore_request: {rescore_correction_id}")
        rescore.status = outcome
        rescore.resulting_run_id = resulting_run_id
        rescore.resulting_extraction_id = resulting_extraction_id
        rescore.completed_at = datetime.now(UTC)

        payload = dict(rescore.payload or {})
        outcome_log = list(payload.get("outcome_log", []))
        outcome_log.append(
            {
                "outcome": outcome.value,
                "recorded_at": rescore.completed_at.isoformat(),
                "resulting_run_id": resulting_run_id,
                "resulting_extraction_id": resulting_extraction_id,
                "diff": diff or {},
                "error": error,
            }
        )
        payload["outcome_log"] = outcome_log
        rescore.payload = payload
        await self.session.commit()
        await self.session.refresh(rescore)

        log_event(
            LOGGER,
            logging.INFO if outcome is not CorrectionStatus.FAILED else logging.WARNING,
            f"correction.rescore.{outcome.value}",
            event_type="correction.rescore",
            status=outcome.value,
            rescore_correction_id=rescore_correction_id,
            source_correction_id=rescore.source_correction_id,
            target_entity_type=str(rescore.target_entity_type),
            target_entity_id=rescore.target_entity_id,
            resulting_run_id=resulting_run_id,
            resulting_extraction_id=resulting_extraction_id,
            workflow_id=rescore.workflow_id,
            error_message=error,
        )
        return rescore
