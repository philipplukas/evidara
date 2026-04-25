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
from datetime import UTC, date, datetime, timedelta
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
from platform_control.schemas.correction import (
    CorrectionMetricsResponse,
    CorrectionMetricsWeek,
    OperatorThroughput,
    RescoreOutcomes,
    RescoreRequest,
    RescoreResponse,
)

DEFAULT_METRICS_LOOKBACK_WEEKS = 12


class _WeekAccumulator:
    """Mutable scratch buffer used while folding rows into one week bucket.

    The Pydantic schema is the public shape; this helper just keeps the
    bucketing loop readable. Counts are converted to ``dict``/``list`` when
    the bucket is finalised so the response models receive immutable
    snapshots.
    """

    __slots__ = (
        "by_entity_type",
        "by_correction_type",
        "operator_throughput",
        "rescore_changed",
        "rescore_unchanged",
        "rescore_failed",
    )

    def __init__(self) -> None:
        self.by_entity_type: dict[str, int] = {}
        self.by_correction_type: dict[str, int] = {}
        self.operator_throughput: dict[str, int] = {}
        self.rescore_changed = 0
        self.rescore_unchanged = 0
        self.rescore_failed = 0


def _iso_week_start(value: datetime) -> date:
    """Return the Monday (UTC) of the ISO week containing ``value``.

    Stable input shape: callers normalise ``value`` to UTC. ``date.weekday()``
    returns 0 for Monday, so subtracting it from the date snaps to the
    week-start without depending on locale.
    """
    if value.tzinfo is None:
        value = value.replace(tzinfo=UTC)
    as_utc = value.astimezone(UTC).date()
    return as_utc - timedelta(days=as_utc.weekday())


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

    async def get_metrics(
        self,
        *,
        since: date | None = None,
        now: datetime | None = None,
    ) -> CorrectionMetricsResponse:
        """Aggregate weekly correction metrics for the dashboard widget (#432).

        ``since`` defaults to ``DEFAULT_METRICS_LOOKBACK_WEEKS`` weeks before
        ``now`` snapped to a Monday so the boundary aligns with the bucket
        Mondays we render. The function performs a single bulk SELECT and
        buckets in Python; weekly aggregation in pure SQL would require
        ``date_trunc`` (Postgres) or ``strftime`` (SQLite) and the
        per-database divergence isn't worth the saved bandwidth at v1
        traffic levels (see the ADR-0009 portability rule).

        Returned weeks are emitted in chronological order, with empty
        bucket rows present so the admin widget can render a stable
        timeline without re-deriving missing weeks.
        """
        now_utc = (now or datetime.now(UTC)).astimezone(UTC)
        if since is None:
            since_monday = _iso_week_start(
                now_utc - timedelta(weeks=DEFAULT_METRICS_LOOKBACK_WEEKS - 1)
            )
        else:
            since_monday = since - timedelta(days=since.weekday())
        since_dt = datetime.combine(since_monday, datetime.min.time(), tzinfo=UTC)

        rows = list(
            await self.session.scalars(
                select(Correction)
                .where(Correction.created_at >= since_dt)
                .order_by(Correction.created_at.asc())
            )
        )

        # Pre-seed the bucket map with every week between ``since`` and
        # ``now`` so the response carries empty weeks instead of gaps —
        # this is what lets the admin chart render a stable axis.
        current_week = _iso_week_start(now_utc)
        weeks: dict[date, _WeekAccumulator] = {}
        cursor = since_monday
        while cursor <= current_week:
            weeks[cursor] = _WeekAccumulator()
            cursor += timedelta(days=7)

        for row in rows:
            week_start = _iso_week_start(row.created_at)
            bucket = weeks.setdefault(week_start, _WeekAccumulator())
            entity_key = (
                row.target_entity_type.value
                if hasattr(row.target_entity_type, "value")
                else str(row.target_entity_type)
            )
            type_key = (
                row.correction_type.value
                if hasattr(row.correction_type, "value")
                else str(row.correction_type)
            )
            bucket.by_entity_type[entity_key] = bucket.by_entity_type.get(entity_key, 0) + 1
            bucket.by_correction_type[type_key] = bucket.by_correction_type.get(type_key, 0) + 1

            # Operator throughput counts ``applied`` operator corrections —
            # pending rows still in the queue do not count as throughput,
            # and platform-emitted ``rescore_request`` rows have no operator.
            if (
                row.status == CorrectionStatus.APPLIED
                and row.correction_type != CorrectionType.RESCORE_REQUEST
                and row.operator_id
            ):
                bucket.operator_throughput[row.operator_id] = (
                    bucket.operator_throughput.get(row.operator_id, 0) + 1
                )

            # Rescore outcomes only consider terminal states.
            if row.correction_type == CorrectionType.RESCORE_REQUEST:
                if row.status == CorrectionStatus.CHANGED:
                    bucket.rescore_changed += 1
                elif row.status == CorrectionStatus.UNCHANGED:
                    bucket.rescore_unchanged += 1
                elif row.status == CorrectionStatus.FAILED:
                    bucket.rescore_failed += 1

        ordered_weeks = [
            CorrectionMetricsWeek(
                week_start=week_start,
                by_entity_type=dict(bucket.by_entity_type),
                by_correction_type=dict(bucket.by_correction_type),
                operator_throughput=[
                    OperatorThroughput(operator_id=operator_id, applied=applied)
                    for operator_id, applied in sorted(
                        bucket.operator_throughput.items(),
                        key=lambda item: (-item[1], item[0]),
                    )
                ],
                rescore_outcomes=RescoreOutcomes(
                    changed=bucket.rescore_changed,
                    unchanged=bucket.rescore_unchanged,
                    failed=bucket.rescore_failed,
                ),
            )
            for week_start, bucket in sorted(weeks.items())
        ]

        return CorrectionMetricsResponse(weeks=ordered_weeks, since=since_monday)

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
