from typing import Annotated

from fastapi import APIRouter, Depends
from sqlalchemy.ext.asyncio import AsyncSession

from platform_control.database import get_session
from platform_control.schemas.source import SourceVersionResponse
from platform_control.services.source_service import SourceService

router = APIRouter(prefix="/v1/versions", tags=["source-versions"])
SessionDep = Annotated[AsyncSession, Depends(get_session)]


@router.post("/{source_version_id}/approve", response_model=SourceVersionResponse)
async def approve_source_version(
    source_version_id: str,
    session: SessionDep,
) -> SourceVersionResponse:
    service = SourceService(session)
    return await service.approve_source_version(source_version_id)


@router.post("/{source_version_id}/reject", response_model=SourceVersionResponse)
async def reject_source_version(
    source_version_id: str,
    session: SessionDep,
) -> SourceVersionResponse:
    service = SourceService(session)
    return await service.reject_source_version(source_version_id)
