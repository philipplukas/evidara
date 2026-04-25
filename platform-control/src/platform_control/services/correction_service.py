"""CorrectionService — CRUD + lifecycle state machine.

Owns the application-layer rules for the corrections audit log:

- Create only ever lands in `pending`.
- Status transitions enforce a small DAG:

      pending  ──→ applied   ──→ superseded
          └──→ rejected

  Anything outside that graph raises :class:`InvalidStateTransitionError`,
  which the global FastAPI exception handler turns into a 409.

- When a transition lands in `applied`, the targeted entity overlay is
  synchronised: for `target_entity_type == 'commentary_insight'` the
  payload is shallow-merged into the `CommentaryInsight` row,
  `overlay_revision` is bumped, and `last_correction_id` is set.

- For `source` and `document` targets the audit log is written but no
  upstream-entity mutation happens here; that wiring is owned by the
  pipeline lanes (#427 rescore, future doc edits).
"""

from __future__ import annotations

from collections import defaultdict
from collections.abc import Callable
from datetime import UTC, datetime, timedelta
from typing import Any

from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from platform_control.errors import (
    ConflictError,
    InvalidStateTransitionError,
    NotFoundError,
)
from platform_control.ids import generate_prefixed_id
from platform_control.models.commentary_insight import CommentaryInsight
from platform_control.models.correction import Correction
from platform_control.schemas.correction import (
    CorrectionStatus,
    CorrectionType,
    CreateCorrectionRequest,
    TargetEntityType,
    UpdateCorrectionStatusRequest,
)

_LEGAL_TRANSITIONS: dict[CorrectionStatus, frozenset[CorrectionStatus]] = {
    CorrectionStatus.PENDING: frozenset({CorrectionStatus.APPLIED, CorrectionStatus.REJECTED}),
    CorrectionStatus.APPLIED: frozenset({CorrectionStatus.SUPERSEDED}),
    CorrectionStatus.REJECTED: frozenset(),
    CorrectionStatus.SUPERSEDED: frozenset(),
}


def _is_legal_transition(current: CorrectionStatus, target: CorrectionStatus) -> bool:
    return target in _LEGAL_TRANSITIONS[current]


class CorrectionService:
    def __init__(self, session: AsyncSession) -> None:
        self.session = session

    async def create(
        self,
        request: CreateCorrectionRequest,
        *,
        operator_id: str,
    ) -> Correction:
        """Persist a new correction in `pending` status.

        For `commentary_insight` targets, validates the target exists so
        we don't accept corrections that could never be applied.
        Returns the full row.
        """

        if request.target_entity_type is TargetEntityType.COMMENTARY_INSIGHT:
            target = await self.session.get(CommentaryInsight, request.target_entity_id)
            if target is None:
                raise NotFoundError(f"CommentaryInsight {request.target_entity_id} does not exist.")

        correction = Correction(
            correction_id=generate_prefixed_id("cor"),
            target_entity_type=request.target_entity_type.value,
            target_entity_id=request.target_entity_id,
            correction_type=request.correction_type.value,
            payload=request.payload,
            original_snapshot=request.original_snapshot,
            operator_id=operator_id,
            pipeline_run_id=request.pipeline_run_id,
            rationale=request.rationale,
            status=CorrectionStatus.PENDING.value,
            created_at=datetime.now(UTC),
            applied_at=None,
        )
        self.session.add(correction)
        await self.session.commit()
        return correction

    async def get(self, correction_id: str) -> Correction:
        row = await self.session.get(Correction, correction_id)
        if row is None:
            raise NotFoundError(f"Correction {correction_id} not found.")
        return row

    async def list(
        self,
        *,
        target_entity_type: TargetEntityType | None = None,
        target_entity_id: str | None = None,
        operator_id: str | None = None,
        status: CorrectionStatus | None = None,
        correction_type: CorrectionType | None = None,
        limit: int = 100,
        offset: int = 0,
    ) -> tuple[list[Correction], int]:
        stmt = select(Correction)
        if target_entity_type is not None:
            stmt = stmt.where(Correction.target_entity_type == target_entity_type.value)
        if target_entity_id is not None:
            stmt = stmt.where(Correction.target_entity_id == target_entity_id)
        if operator_id is not None:
            stmt = stmt.where(Correction.operator_id == operator_id)
        if status is not None:
            stmt = stmt.where(Correction.status == status.value)
        if correction_type is not None:
            stmt = stmt.where(Correction.correction_type == correction_type.value)
        # `created_at DESC` mirrors the admin queue's natural read order.
        stmt = stmt.order_by(Correction.created_at.desc())
        all_matching = (await self.session.scalars(stmt)).all()
        total = len(all_matching)
        page = list(all_matching[offset : offset + limit])
        return page, total

    async def update_status(
        self,
        correction_id: str,
        request: UpdateCorrectionStatusRequest,
    ) -> Correction:
        row = await self.get(correction_id)
        current = CorrectionStatus(row.status)
        target = request.status

        if not _is_legal_transition(current, target):
            raise InvalidStateTransitionError(
                f"Illegal correction status transition: {current.value} → {target.value}. "
                f"Allowed targets from {current.value}: "
                f"{sorted(s.value for s in _LEGAL_TRANSITIONS[current])}."
            )

        row.status = target.value
        if request.rationale is not None:
            row.rationale = request.rationale

        if target is CorrectionStatus.APPLIED:
            row.applied_at = datetime.now(UTC)
            await self._apply_to_overlay(row)

        await self.session.commit()
        return row

    async def trigger_rescore(
        self,
        correction_id: str,
        *,
        scheduler: Any,
    ) -> dict[str, Any]:
        """Schedule the rescore-from-correction workflow (#427).

        Validates that the target correction is a `rescore_request` and
        is still actionable (status `pending` or `applied`). Idempotent:
        re-firing on a correction that already has `triggered_workflow_id`
        in its payload returns the existing workflow handle without
        rescheduling. After a successful schedule, the correction's
        payload records `triggered_workflow_id` + `triggered_at` so the
        admin queue and metrics dashboard can trace correction → run.

        The actual workflow execution (and writing back
        `resulting_run_id` / `rescore_outcome`) lives in the activity
        (`platform_control.temporal.activities.rescore_from_correction`).
        """

        row = await self.get(correction_id)
        if row.correction_type != CorrectionType.RESCORE_REQUEST.value:
            raise ConflictError(
                f"Correction {correction_id} has type {row.correction_type!r}; "
                f"only `rescore_request` corrections can trigger a rescore."
            )
        if row.status not in {
            CorrectionStatus.PENDING.value,
            CorrectionStatus.APPLIED.value,
        }:
            raise ConflictError(
                f"Correction {correction_id} status is {row.status!r}; "
                f"rescore can only be triggered while pending or applied."
            )

        payload = dict(row.payload or {})
        if isinstance(payload.get("triggered_workflow_id"), str):
            # Idempotent re-fire: same correction, return the prior handle.
            return {
                "correction_id": correction_id,
                "workflow_id": payload["triggered_workflow_id"],
                "already_running": True,
                "triggered_at": payload.get("triggered_at"),
            }

        result = await scheduler.schedule(
            correction_id=row.correction_id,
            target_entity_type=row.target_entity_type,
            target_entity_id=row.target_entity_id,
            payload=payload,
        )

        triggered_at = datetime.now(UTC).isoformat()
        payload["triggered_workflow_id"] = result.workflow_id
        payload["triggered_at"] = triggered_at
        row.payload = payload
        await self.session.commit()

        return {
            "correction_id": correction_id,
            "workflow_id": result.workflow_id,
            "already_running": result.already_running,
            "triggered_at": triggered_at,
        }

    async def record_rescore_outcome(
        self,
        correction_id: str,
        *,
        outcome: str,
        resulting_run_id: str | None = None,
    ) -> Correction:
        """Persist the rescore worker's outcome on the correction's payload.

        Called by `platform_control.temporal.activities.rescore_from_correction`
        once the DI re-extraction returns. Outcome is one of `changed` /
        `unchanged` / `failed`; the correction-metrics widget (#432)
        reads `payload.rescore_outcome` to populate the rescore counters.
        """

        if outcome not in {"changed", "unchanged", "failed"}:
            raise ValueError(
                f"rescore_outcome must be one of changed/unchanged/failed, got {outcome!r}."
            )
        row = await self.get(correction_id)
        payload = dict(row.payload or {})
        payload["rescore_outcome"] = outcome
        if resulting_run_id is not None:
            payload["resulting_run_id"] = resulting_run_id
        payload["completed_at"] = datetime.now(UTC).isoformat()
        row.payload = payload
        await self.session.commit()
        return row

    async def list_for_target(
        self,
        *,
        target_entity_type: TargetEntityType,
        target_entity_id: str,
    ) -> list[Correction]:
        """Audit-log read for a single target, oldest first.

        Used by the commentary-insight history endpoint. Returns rows in
        creation order so the UI renders a forward-in-time timeline.
        """

        stmt = (
            select(Correction)
            .where(Correction.target_entity_type == target_entity_type.value)
            .where(Correction.target_entity_id == target_entity_id)
            .order_by(Correction.created_at.asc())
        )
        return list((await self.session.scalars(stmt)).all())

    async def get_metrics(
        self,
        *,
        window_weeks: int = 8,
        operator_throughput_window_days: int = 30,
        operator_throughput_top_n: int = 10,
        now: datetime | None = None,
    ) -> dict[str, Any]:
        """Aggregate read model for the admin metrics dashboard (#432).

        Computed entirely from the corrections audit log; no new
        telemetry store. Aggregation runs in Python after a single
        bounded fetch (rows in the configured window) — keeps the
        SQL portable across SQLite + Postgres without dialect-specific
        date_trunc calls.
        """

        if window_weeks < 1 or window_weeks > 52:
            raise ValueError("window_weeks must be between 1 and 52")
        if operator_throughput_window_days < 1 or operator_throughput_window_days > 365:
            raise ValueError("operator_throughput_window_days must be between 1 and 365")

        as_of = now or datetime.now(UTC)
        weekly_window_start = _floor_to_week_start(as_of - timedelta(weeks=window_weeks - 1))
        ops_window_start = as_of - timedelta(days=operator_throughput_window_days)
        fetch_start = min(weekly_window_start, ops_window_start)

        stmt = select(Correction).where(Correction.created_at >= fetch_start)
        rows = list((await self.session.scalars(stmt)).all())

        weekly_target = _aggregate_weekly_groups(
            rows,
            window_weeks=window_weeks,
            window_start=weekly_window_start,
            grouper=lambda r: r.target_entity_type,
        )
        weekly_type = _aggregate_weekly_groups(
            rows,
            window_weeks=window_weeks,
            window_start=weekly_window_start,
            grouper=lambda r: r.correction_type,
        )
        operator_throughput = _aggregate_operator_throughput(
            [r for r in rows if _ensure_utc(r.created_at) >= ops_window_start],
            top_n=operator_throughput_top_n,
        )
        rescore_outcomes = _aggregate_rescore_outcomes(rows)

        return {
            "window_weeks": window_weeks,
            "operator_throughput_window_days": operator_throughput_window_days,
            "weekly_by_target_entity_type": weekly_target,
            "weekly_by_correction_type": weekly_type,
            "operator_throughput": operator_throughput,
            "rescore_outcomes": rescore_outcomes,
        }

    async def _apply_to_overlay(self, correction: Correction) -> None:
        """Sync an applied correction into the targeted entity overlay.

        Currently scoped to commentary insights; source/document overlay
        application lands with the rescore lane (#427) and future doc-edit
        work. Field edits do a shallow merge against the cached overlay
        row; rejects mark the row as `rejected` review_state; annotations
        are audit-only and don't touch the overlay; rescore_request is
        always audit-only and the worker side handles re-processing.
        """

        if correction.target_entity_type != TargetEntityType.COMMENTARY_INSIGHT.value:
            return
        target = await self.session.get(CommentaryInsight, correction.target_entity_id)
        if target is None:
            # We validated existence on create; if it's gone now, that's a
            # data-integrity issue — surface as 409 so the operator can
            # investigate rather than silently no-op.
            raise ConflictError(
                f"CommentaryInsight {correction.target_entity_id} disappeared "
                f"between correction creation and application."
            )

        ctype = CorrectionType(correction.correction_type)
        if ctype is CorrectionType.FIELD_EDIT:
            self._apply_field_edit(target, correction.payload)
        elif ctype is CorrectionType.REJECT:
            target.review_state = "rejected"
        # ANNOTATION and RESCORE_REQUEST: audit-only, no overlay change.

        target.overlay_revision += 1
        target.last_correction_id = correction.correction_id

    @staticmethod
    def _apply_field_edit(target: CommentaryInsight, payload: dict[str, Any]) -> None:
        """Apply a single field_edit payload `{field, value}` to the overlay.

        Conservative: only fields explicitly safe for in-place edit are
        accepted. Unknown fields raise so we don't accidentally let an
        operator overwrite primary-key or pipeline-derived state.
        """

        field = payload.get("field")
        value = payload.get("value")
        if not isinstance(field, str):
            raise ConflictError("field_edit payload must include a string `field` key.")
        editable_fields = {
            "claim",
            "display_text",
            "language",
            "jurisdiction_id",
            "review_state",
        }
        if field not in editable_fields:
            raise ConflictError(
                f"field_edit on {field!r} is not permitted via correction. "
                f"Editable fields: {sorted(editable_fields)}."
            )
        setattr(target, field, value)


# ─── Metrics aggregation helpers (#432) ────────────────────────────────────


def _ensure_utc(value: datetime) -> datetime:
    """Normalise a possibly-naive datetime to UTC.

    SQLite returns naive datetimes via aiosqlite; Postgres returns
    timezone-aware. Treat naive as UTC so the comparisons below stay
    correct on both backends.
    """

    if value.tzinfo is None:
        return value.replace(tzinfo=UTC)
    return value.astimezone(UTC)


def _floor_to_week_start(value: datetime) -> datetime:
    """Floor a datetime to 00:00 UTC of the Monday of its ISO week."""

    aware = _ensure_utc(value)
    days_since_monday = aware.weekday()
    monday = aware - timedelta(days=days_since_monday)
    return monday.replace(hour=0, minute=0, second=0, microsecond=0)


def _aggregate_weekly_groups(
    rows: list[Any],
    *,
    window_weeks: int,
    window_start: datetime,
    grouper: Callable[[Any], str],
) -> list[dict[str, Any]]:
    """Bucket rows into ISO-week buckets per group key.

    Returns one entry per distinct group key, each carrying exactly
    `window_weeks` buckets (oldest week first). Keys are sorted
    alphabetically for deterministic output.
    """

    bucket_starts = [(window_start + timedelta(weeks=i)) for i in range(window_weeks)]
    bucket_lookup = {bucket.date().isoformat(): i for i, bucket in enumerate(bucket_starts)}
    counts: dict[str, list[int]] = defaultdict(lambda: [0] * window_weeks)

    for row in rows:
        created = _ensure_utc(row.created_at)
        if created < window_start:
            continue
        bucket = _floor_to_week_start(created)
        idx = bucket_lookup.get(bucket.date().isoformat())
        if idx is None:
            continue
        counts[grouper(row)][idx] += 1

    series: list[dict[str, Any]] = []
    for key in sorted(counts.keys()):
        series.append(
            {
                "key": key,
                "buckets": [
                    {
                        "week_start": bucket_starts[i].date().isoformat(),
                        "count": counts[key][i],
                    }
                    for i in range(window_weeks)
                ],
            }
        )
    return series


def _aggregate_operator_throughput(
    rows: list[Any],
    *,
    top_n: int,
) -> list[dict[str, Any]]:
    """Per-operator total / applied / rejected counts in the window.

    Returned list is sorted by total desc, then operator_id asc for
    deterministic ordering. Truncated to `top_n` entries.
    """

    by_op: dict[str, dict[str, int]] = defaultdict(
        lambda: {"total": 0, "applied": 0, "rejected": 0}
    )
    for row in rows:
        bucket = by_op[row.operator_id]
        bucket["total"] += 1
        if row.status == "applied":
            bucket["applied"] += 1
        elif row.status == "rejected":
            bucket["rejected"] += 1

    sorted_entries = sorted(
        by_op.items(),
        key=lambda kv: (-kv[1]["total"], kv[0]),
    )[:top_n]
    return [
        {
            "operator_id": op_id,
            "total": vals["total"],
            "applied": vals["applied"],
            "rejected": vals["rejected"],
        }
        for op_id, vals in sorted_entries
    ]


def _aggregate_rescore_outcomes(rows: list[Any]) -> dict[str, int]:
    """Count `rescore_request` corrections by status.

    `changed`/`unchanged`/`failed` are populated from the correction's
    payload (set by the rescore worker — #427). Until that lane lands,
    those counters are zero.
    """

    pending = 0
    applied_total = 0
    rejected = 0
    changed = 0
    unchanged = 0
    failed = 0
    for row in rows:
        if row.correction_type != "rescore_request":
            continue
        if row.status == "pending":
            pending += 1
        elif row.status == "applied":
            applied_total += 1
            outcome = row.payload.get("rescore_outcome") if isinstance(row.payload, dict) else None
            if outcome == "changed":
                changed += 1
            elif outcome == "unchanged":
                unchanged += 1
            elif outcome == "failed":
                failed += 1
        elif row.status == "rejected":
            rejected += 1
    return {
        "pending": pending,
        "applied_total": applied_total,
        "rejected": rejected,
        "changed": changed,
        "unchanged": unchanged,
        "failed": failed,
    }
