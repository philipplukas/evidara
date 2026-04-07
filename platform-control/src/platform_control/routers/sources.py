from typing import Annotated

from fastapi import APIRouter, Depends, status
from sqlalchemy.ext.asyncio import AsyncSession

from platform_control.database import get_session
from platform_control.schemas.source import (
    CreateSourceRequest,
    CreateSourceVersionRequest,
    SourceListResponse,
    SourceResponse,
    SourceVersionListResponse,
    SourceVersionResponse,
)
from platform_control.services.source_service import SourceService

router = APIRouter(prefix="/v1/sources", tags=["sources", "source-versions"])
SessionDep = Annotated[AsyncSession, Depends(get_session)]


@router.get("", response_model=SourceListResponse)
async def list_sources(
    session: SessionDep,
    limit: int = 100,
    offset: int = 0,
    q: str | None = None,
) -> SourceListResponse:
    service = SourceService(session)
    clamped_limit = max(1, min(limit, 500))
    clamped_offset = max(0, offset)
    data, total = await service.list_sources(limit=clamped_limit, offset=clamped_offset, q=q)
    return SourceListResponse(data=data, total=total, limit=clamped_limit, offset=clamped_offset)


@router.post("", response_model=SourceResponse, status_code=status.HTTP_201_CREATED)
async def create_source(
    request: CreateSourceRequest,
    session: SessionDep,
) -> SourceResponse:
    service = SourceService(session)
    return await service.create_source(request)


@router.get("/{source_id}", response_model=SourceResponse)
async def get_source(
    source_id: str,
    session: SessionDep,
) -> SourceResponse:
    service = SourceService(session)
    return await service.get_source(source_id)


@router.get("/{source_id}/versions", response_model=SourceVersionListResponse)
async def list_source_versions(
    source_id: str,
    session: SessionDep,
) -> SourceVersionListResponse:
    service = SourceService(session)
    return SourceVersionListResponse(data=await service.list_source_versions(source_id))


@router.post(
    "/{source_id}/versions",
    response_model=SourceVersionResponse,
    status_code=status.HTTP_201_CREATED,
)
async def create_source_version(
    source_id: str,
    request: CreateSourceVersionRequest,
    session: SessionDep,
) -> SourceVersionResponse:
    service = SourceService(session)
    return await service.create_source_version(source_id, request)
