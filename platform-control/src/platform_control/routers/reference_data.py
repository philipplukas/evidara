from pathlib import Path
from typing import Annotated

from fastapi import APIRouter, Depends, Query, status
from sqlalchemy.ext.asyncio import AsyncSession

from platform_control.database import get_session
from platform_control.schemas.reference_data import (
    AuthorityListResponse,
    AuthorityResponse,
    CreateAuthorityRequest,
    CreateJurisdictionRequest,
    HierarchySyncCountsResponse,
    HierarchySyncResponse,
    JurisdictionListResponse,
    JurisdictionResponse,
    UpdateAuthorityRequest,
    UpdateJurisdictionRequest,
)
from platform_control.services.hierarchy_sync_service import HierarchySyncService
from platform_control.services.reference_data_service import ReferenceDataService

router = APIRouter(prefix="/v1/reference-data", tags=["reference-data"])
SessionDep = Annotated[AsyncSession, Depends(get_session)]
DEFAULT_HIERARCHY_DIR = Path(__file__).resolve().parents[3] / "hierarchies"


@router.get("/jurisdictions", response_model=JurisdictionListResponse)
async def list_jurisdictions(session: SessionDep) -> JurisdictionListResponse:
    service = ReferenceDataService(session)
    return JurisdictionListResponse(data=await service.list_jurisdictions())


@router.post(
    "/jurisdictions",
    response_model=JurisdictionResponse,
    status_code=status.HTTP_201_CREATED,
)
async def create_jurisdiction(
    request: CreateJurisdictionRequest,
    session: SessionDep,
) -> JurisdictionResponse:
    service = ReferenceDataService(session)
    return await service.create_jurisdiction(request)


@router.patch("/jurisdictions/{jurisdiction_id}", response_model=JurisdictionResponse)
async def update_jurisdiction(
    jurisdiction_id: str,
    request: UpdateJurisdictionRequest,
    session: SessionDep,
) -> JurisdictionResponse:
    service = ReferenceDataService(session)
    return await service.update_jurisdiction(jurisdiction_id, request)


@router.get("/authorities", response_model=AuthorityListResponse)
async def list_authorities(session: SessionDep) -> AuthorityListResponse:
    service = ReferenceDataService(session)
    return AuthorityListResponse(data=await service.list_authorities())


@router.post(
    "/authorities",
    response_model=AuthorityResponse,
    status_code=status.HTTP_201_CREATED,
)
async def create_authority(
    request: CreateAuthorityRequest,
    session: SessionDep,
) -> AuthorityResponse:
    service = ReferenceDataService(session)
    return await service.create_authority(request)


@router.patch("/authorities/{authority_id}", response_model=AuthorityResponse)
async def update_authority(
    authority_id: str,
    request: UpdateAuthorityRequest,
    session: SessionDep,
) -> AuthorityResponse:
    service = ReferenceDataService(session)
    return await service.update_authority(authority_id, request)


@router.post("/hierarchy/sync", response_model=HierarchySyncResponse)
async def sync_hierarchy(
    session: SessionDep,
    dry_run: bool = Query(default=False),
) -> HierarchySyncResponse:
    summary = await HierarchySyncService(session).sync(DEFAULT_HIERARCHY_DIR, dry_run=dry_run)
    return HierarchySyncResponse(
        dry_run=dry_run,
        jurisdictions=HierarchySyncCountsResponse(
            created=summary.jurisdictions.created,
            updated=summary.jurisdictions.updated,
            unchanged=summary.jurisdictions.unchanged,
        ),
        authorities=HierarchySyncCountsResponse(
            created=summary.authorities.created,
            updated=summary.authorities.updated,
            unchanged=summary.authorities.unchanged,
        ),
        scrape_targets=HierarchySyncCountsResponse(
            created=summary.scrape_targets.created,
            updated=summary.scrape_targets.updated,
            unchanged=summary.scrape_targets.unchanged,
        ),
    )
