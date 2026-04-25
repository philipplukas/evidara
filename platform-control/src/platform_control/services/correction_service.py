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

from datetime import UTC, datetime
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
