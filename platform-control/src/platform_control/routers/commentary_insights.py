"""HTTP surface for commentary-insight overlay reads.

Three endpoints, all read-only — writes flow through the corrections
audit log (`POST /v1/corrections` followed by
`PATCH /v1/corrections/{id}` to apply). See PR #434 for the contract
freeze rationale.
"""

from __future__ import annotations

from typing import Annotated

from fastapi import APIRouter, Depends, Query
from sqlalchemy.ext.asyncio import AsyncSession

from platform_control.database import get_session
from platform_control.schemas.commentary_insight import (
    CommentaryInsightHistoryEntry,
    CommentaryInsightHistoryResponse,
    CommentaryInsightListResponse,
    CommentaryInsightResponse,
)
from platform_control.services.commentary_insight_service import (
    CommentaryInsightService,
)

router = APIRouter(prefix="/v1", tags=["commentary-insights"])
SessionDep = Annotated[AsyncSession, Depends(get_session)]


@router.get(
    "/commentary-insights",
    response_model=CommentaryInsightListResponse,
)
async def list_commentary_insights(
    session: SessionDep,
    document_id: Annotated[str | None, Query()] = None,
    review_state: Annotated[str | None, Query()] = None,
    limit: Annotated[int, Query(ge=1, le=500)] = 100,
    offset: Annotated[int, Query(ge=0)] = 0,
) -> CommentaryInsightListResponse:
    service = CommentaryInsightService(session)
    rows, total = await service.list(
        document_id=document_id,
        review_state=review_state,
        limit=limit,
        offset=offset,
    )
    return CommentaryInsightListResponse(
        data=[CommentaryInsightResponse.model_validate(row, from_attributes=True) for row in rows],
        total=total,
        limit=limit,
        offset=offset,
    )


@router.get(
    "/commentary-insights/{insight_id}",
    response_model=CommentaryInsightResponse,
)
async def get_commentary_insight(
    insight_id: str,
    session: SessionDep,
) -> CommentaryInsightResponse:
    service = CommentaryInsightService(session)
    row = await service.get(insight_id)
    return CommentaryInsightResponse.model_validate(row, from_attributes=True)


@router.get(
    "/commentary-insights/{insight_id}/history",
    response_model=CommentaryInsightHistoryResponse,
)
async def get_commentary_insight_history(
    insight_id: str,
    session: SessionDep,
) -> CommentaryInsightHistoryResponse:
    service = CommentaryInsightService(session)
    insight, corrections = await service.history(insight_id)
    return CommentaryInsightHistoryResponse(
        insight_id=insight.insight_id,
        overlay_revision=insight.overlay_revision,
        history=[
            CommentaryInsightHistoryEntry.model_validate(row, from_attributes=True)
            for row in corrections
        ],
    )
