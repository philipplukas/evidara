from typing import Annotated

from fastapi import APIRouter, Depends
from sqlalchemy.ext.asyncio import AsyncSession

from platform_control.database import get_session
from platform_control.schemas.errors import error_responses
from platform_control.schemas.source import SourceVersionResponse, UpdateSourceVersionRequest
from platform_control.services.source_service import SourceService

router = APIRouter(prefix="/v1/versions", tags=["source-versions"])
SessionDep = Annotated[AsyncSession, Depends(get_session)]


@router.post(
    "/{source_version_id}/approve",
    response_model=SourceVersionResponse,
    responses=error_responses(404, 409),
)
async def approve_source_version(
    source_version_id: str,
    session: SessionDep,
) -> SourceVersionResponse:
    service = SourceService(session)
    return await service.approve_source_version(source_version_id)


@router.patch(
    "/{source_version_id}",
    response_model=SourceVersionResponse,
    responses=error_responses(404, 409),
)
async def update_source_version(
    source_version_id: str,
    request: UpdateSourceVersionRequest,
    session: SessionDep,
) -> SourceVersionResponse:
    service = SourceService(session)
    return await service.update_source_version(source_version_id, request)


@router.post(
    "/{source_version_id}/reject",
    response_model=SourceVersionResponse,
    responses=error_responses(404, 409),
)
async def reject_source_version(
    source_version_id: str,
    session: SessionDep,
) -> SourceVersionResponse:
    service = SourceService(session)
    return await service.reject_source_version(source_version_id)
