"""Read/queue helpers for the :class:`Correction` audit log.

Most writes happen inside other services (e.g. CommentaryInsightService writes
a ``field_edit`` row when a patch is applied). This module is the operator
read surface — list pending corrections, scope by entity type, and so on.
"""

from __future__ import annotations

from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from platform_control.domain import (
    CorrectionStatus,
    CorrectionTargetEntityType,
    CorrectionType,
)
from platform_control.errors import NotFoundError
from platform_control.models.correction import Correction


class CorrectionService:
    def __init__(self, session: AsyncSession) -> None:
        self.session = session

    async def get(self, correction_id: str) -> Correction:
        row = await self.session.get(Correction, correction_id)
        if row is None:
            raise NotFoundError(f"Correction not found: {correction_id}")
        return row

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
