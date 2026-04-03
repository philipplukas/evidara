from typing import Annotated

from fastapi import APIRouter, Depends, status
from sqlalchemy.ext.asyncio import AsyncSession

from platform_control.database import get_session
from platform_control.schemas.reference_data import (
    AuthorityListResponse,
    AuthorityResponse,
    CreateAuthorityRequest,
    CreateJurisdictionRequest,
    JurisdictionListResponse,
    JurisdictionResponse,
    UpdateAuthorityRequest,
    UpdateJurisdictionRequest,
)
from platform_control.services.reference_data_service import ReferenceDataService

router = APIRouter(prefix="/v1/reference-data", tags=["reference-data"])
SessionDep = Annotated[AsyncSession, Depends(get_session)]


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
