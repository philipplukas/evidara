"""CommentaryInsightService — read-only overlay access.

Writes to commentary insights flow through `CorrectionService.update_status`
(when an applied correction targets an insight). This service handles
read traffic: list / get / per-insight history.
"""

from __future__ import annotations

from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from platform_control.errors import NotFoundError
from platform_control.models.commentary_insight import CommentaryInsight
from platform_control.models.correction import Correction


class CommentaryInsightService:
    def __init__(self, session: AsyncSession) -> None:
        self.session = session

    async def list(
        self,
        *,
        document_id: str | None = None,
        review_state: str | None = None,
        limit: int = 100,
        offset: int = 0,
    ) -> tuple[list[CommentaryInsight], int]:
        stmt = select(CommentaryInsight)
        if document_id is not None:
            stmt = stmt.where(CommentaryInsight.document_id == document_id)
        if review_state is not None:
            stmt = stmt.where(CommentaryInsight.review_state == review_state)
        stmt = stmt.order_by(CommentaryInsight.updated_at.desc())
        all_matching = (await self.session.scalars(stmt)).all()
        total = len(all_matching)
        page = list(all_matching[offset : offset + limit])
        return page, total

    async def get(self, insight_id: str) -> CommentaryInsight:
        row = await self.session.get(CommentaryInsight, insight_id)
        if row is None:
            raise NotFoundError(f"CommentaryInsight {insight_id} not found.")
        return row

    async def history(self, insight_id: str) -> tuple[CommentaryInsight, list[Correction]]:
        """Return the insight + every correction that has targeted it, oldest first."""

        insight = await self.get(insight_id)
        stmt = (
            select(Correction)
            .where(Correction.target_entity_type == "commentary_insight")
            .where(Correction.target_entity_id == insight_id)
            .order_by(Correction.created_at.asc())
        )
        corrections = list((await self.session.scalars(stmt)).all())
        return insight, corrections
