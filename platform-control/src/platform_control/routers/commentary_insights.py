from __future__ import annotations

from typing import Annotated

from fastapi import APIRouter, Depends, Query
from sqlalchemy.ext.asyncio import AsyncSession

from platform_control.database import get_session
from platform_control.domain import (
    CommentaryInsightReviewState,
    CorrectionTargetEntityType,
)
from platform_control.schemas.commentary_insight import (
    CommentaryInsightListResponse,
    CommentaryInsightResponse,
    PatchCommentaryInsightRequest,
)
from platform_control.schemas.correction import (
    CorrectionListResponse,
    CorrectionResponse,
)
from platform_control.services.commentary_insight_service import CommentaryInsightService
from platform_control.services.correction_service import CorrectionService

router = APIRouter(prefix="/v1", tags=["commentary-insights"])
SessionDep = Annotated[AsyncSession, Depends(get_session)]


@router.get(
    "/commentary-insights",
    response_model=CommentaryInsightListResponse,
)
async def list_commentary_insights(
    session: SessionDep,
    jurisdiction_id: Annotated[str | None, Query()] = None,
    authority_id: Annotated[str | None, Query()] = None,
    source_document_id: Annotated[str | None, Query()] = None,
    review_state: Annotated[CommentaryInsightReviewState | None, Query()] = None,
    limit: Annotated[int, Query(ge=1, le=500)] = 50,
) -> CommentaryInsightListResponse:
    service = CommentaryInsightService(session)
    rows = await service.list_insights(
        jurisdiction_id=jurisdiction_id,
        authority_id=authority_id,
        source_document_id=source_document_id,
        review_state=review_state.value if review_state else None,
        limit=limit,
    )
    return CommentaryInsightListResponse(
        data=[CommentaryInsightResponse.from_orm_row(row) for row in rows]
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
    row = await service.get_insight(insight_id)
    return CommentaryInsightResponse.from_orm_row(row)


@router.patch(
    "/commentary-insights/{insight_id}",
    response_model=CommentaryInsightResponse,
)
async def patch_commentary_insight(
    insight_id: str,
    request: PatchCommentaryInsightRequest,
    session: SessionDep,
) -> CommentaryInsightResponse:
    service = CommentaryInsightService(session)
    row = await service.apply_field_edit(insight_id, request)
    return CommentaryInsightResponse.from_orm_row(row)


@router.get(
    "/commentary-insights/{insight_id}/history",
    response_model=CorrectionListResponse,
)
async def get_commentary_insight_history(
    insight_id: str,
    session: SessionDep,
    limit: Annotated[int, Query(ge=1, le=1000)] = 200,
) -> CorrectionListResponse:
    # 404 if the insight itself doesn't exist — surface the right error to the
    # operator instead of silently returning an empty history.
    insight_service = CommentaryInsightService(session)
    await insight_service.get_insight(insight_id)

    correction_service = CorrectionService(session)
    rows = await correction_service.list_history_for_entity(
        target_entity_type=CorrectionTargetEntityType.COMMENTARY_INSIGHT,
        target_entity_id=insight_id,
        limit=limit,
    )
    return CorrectionListResponse(data=[CorrectionResponse.model_validate(row) for row in rows])
