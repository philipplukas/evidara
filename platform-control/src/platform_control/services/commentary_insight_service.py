"""CRUD + patch-apply logic for commentary insight overlays.

The ``apply_field_edit`` flow is the load-bearing piece: every operator PATCH
must (a) write a ``field_edit`` :class:`Correction` row, (b) verify the
operator was looking at the same field values we currently hold (optimistic
concurrency), (c) apply the patch to the overlay row, and (d) link the row
back to the correction. All four happen in a single transaction so a partial
failure can never leave the audit log out of sync with the overlay.
"""

from __future__ import annotations

from datetime import UTC, datetime
from typing import Any

from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from platform_control.domain import (
    CorrectionStatus,
    CorrectionTargetEntityType,
    CorrectionType,
)
from platform_control.errors import ConflictError, NotFoundError
from platform_control.models.commentary_insight import CommentaryInsight
from platform_control.models.correction import Correction
from platform_control.schemas.commentary_insight import (
    EDITABLE_FIELDS,
    PatchCommentaryInsightRequest,
)


class CommentaryInsightService:
    def __init__(self, session: AsyncSession) -> None:
        self.session = session

    async def list_insights(
        self,
        *,
        jurisdiction_id: str | None = None,
        authority_id: str | None = None,
        source_document_id: str | None = None,
        review_state: str | None = None,
        limit: int = 50,
    ) -> list[CommentaryInsight]:
        stmt = select(CommentaryInsight)
        if jurisdiction_id is not None:
            stmt = stmt.where(CommentaryInsight.jurisdiction_id == jurisdiction_id)
        if authority_id is not None:
            stmt = stmt.where(CommentaryInsight.authority_id == authority_id)
        if source_document_id is not None:
            # CONTRACT-PENDING #423: source_document_id is the issue's term;
            # the contract calls this field document_id. Treat them as
            # equivalent at the query layer until the freeze settles.
            stmt = stmt.where(CommentaryInsight.document_id == source_document_id)
        if review_state is not None:
            stmt = stmt.where(CommentaryInsight.review_state == review_state)
        stmt = stmt.order_by(CommentaryInsight.overlay_updated_at.desc()).limit(limit)
        result = await self.session.scalars(stmt)
        return list(result)

    async def get_insight(self, insight_id: str) -> CommentaryInsight:
        row = await self.session.get(CommentaryInsight, insight_id)
        if row is None:
            raise NotFoundError(f"CommentaryInsight not found: {insight_id}")
        return row

    async def apply_field_edit(
        self,
        insight_id: str,
        request: PatchCommentaryInsightRequest,
    ) -> CommentaryInsight:
        """Atomically apply a field edit and append the audit row.

        Optimistic-concurrency rule: the operator must submit
        ``original_snapshot`` containing the *current* value of every patched
        field. If any value disagrees with what's persisted we reject the
        request with :class:`ConflictError` so the operator has to refresh and
        re-evaluate the change against the new state.
        """
        row = await self.get_insight(insight_id)

        # Check the snapshot against current state — extracting only the
        # fields the patch actually touches keeps the operator from being
        # forced to send the whole document.
        current_snapshot = self._extract_snapshot(row, request.patch.keys())
        mismatched = {
            field: {"expected": request.original_snapshot[field], "actual": current_snapshot[field]}
            for field in request.patch
            if request.original_snapshot.get(field) != current_snapshot[field]
        }
        if mismatched:
            raise ConflictError(
                "CommentaryInsight has changed since the snapshot was taken; "
                f"mismatched fields: {sorted(mismatched.keys())}"
            )

        applied_at = datetime.now(UTC)
        correction = Correction(
            target_entity_type=CorrectionTargetEntityType.COMMENTARY_INSIGHT,
            target_entity_id=insight_id,
            correction_type=CorrectionType.FIELD_EDIT,
            payload=dict(request.patch),
            original_snapshot=dict(current_snapshot),
            operator_id=request.operator_id,
            pipeline_run_id=request.pipeline_run_id,
            rationale=request.rationale,
            status=CorrectionStatus.APPLIED,
            applied_at=applied_at,
        )
        self.session.add(correction)
        await self.session.flush()  # populate correction_id

        # Apply the patch in-place.
        for field, value in request.patch.items():
            self._set_overlay_field(row, field, value)
        row.current_version += 1
        row.last_correction_id = correction.correction_id
        row.overlay_updated_at = applied_at

        await self.session.commit()
        await self.session.refresh(row)
        return row

    @staticmethod
    def _extract_snapshot(row: CommentaryInsight, fields: Any) -> dict[str, Any]:
        snapshot: dict[str, Any] = {}
        for field in fields:
            if field not in EDITABLE_FIELDS:
                # Defensive — the schema layer should already have rejected
                # this, but we never trust the request to be pre-validated.
                continue
            snapshot[field] = CommentaryInsightService._get_overlay_field(row, field)
        return snapshot

    @staticmethod
    def _get_overlay_field(row: CommentaryInsight, field: str) -> Any:
        if field == "metadata":
            return row.extra_metadata
        return getattr(row, field)

    @staticmethod
    def _set_overlay_field(row: CommentaryInsight, field: str, value: Any) -> None:
        if field == "metadata":
            row.extra_metadata = value
            return
        setattr(row, field, value)
