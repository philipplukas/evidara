from __future__ import annotations

from typing import Annotated

from fastapi import APIRouter, Depends, Query
from sqlalchemy.ext.asyncio import AsyncSession

from platform_control.database import get_session
from platform_control.domain import (
    CorrectionStatus,
    CorrectionTargetEntityType,
    CorrectionType,
)
from platform_control.schemas.correction import (
    CorrectionListResponse,
    CorrectionResponse,
)
from platform_control.services.correction_service import CorrectionService

router = APIRouter(prefix="/v1", tags=["corrections"])
SessionDep = Annotated[AsyncSession, Depends(get_session)]


@router.get(
    "/corrections/queue",
    response_model=CorrectionListResponse,
)
async def list_correction_queue(
    session: SessionDep,
    target_entity_type: Annotated[CorrectionTargetEntityType | None, Query()] = None,
    correction_type: Annotated[CorrectionType | None, Query()] = None,
    status: Annotated[CorrectionStatus, Query()] = CorrectionStatus.PENDING,
    limit: Annotated[int, Query(ge=1, le=500)] = 50,
) -> CorrectionListResponse:
    service = CorrectionService(session)
    rows = await service.list_queue(
        target_entity_type=target_entity_type,
        correction_type=correction_type,
        status=status,
        limit=limit,
    )
    return CorrectionListResponse(data=[CorrectionResponse.model_validate(row) for row in rows])
