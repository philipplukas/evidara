from typing import Annotated

from fastapi import APIRouter, Depends, Query, status
from sqlalchemy.ext.asyncio import AsyncSession

from platform_control.database import get_session, get_session_maker
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
from platform_control.seed_reference_data import DEFAULT_SEED_DIR, ReferenceDataSeeder
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


@router.post("/hierarchy/sync", response_model=HierarchySyncResponse)
async def sync_hierarchy(
    session: SessionDep,
    dry_run: bool = Query(default=False),
) -> HierarchySyncResponse:
    # Backwards-compatible shim over ReferenceDataSeeder (issue #312). The
    # legacy HierarchySyncService and its path-based YAMLs are gone; the
    # canonical `seeds/reference/` bundles are the single source of truth.
    # `scrape_targets` is kept in the response with zeros for shape
    # compatibility with `scripts/e2e-smoke-test.sh` and other callers.
    seeder = ReferenceDataSeeder(get_session_maker())
    summary = await seeder.seed_with_session(session, DEFAULT_SEED_DIR, dry_run=dry_run)
    return HierarchySyncResponse(
        dry_run=dry_run,
        jurisdictions=HierarchySyncCountsResponse(
            created=summary.created["jurisdictions"],
            updated=summary.updated["jurisdictions"],
            unchanged=summary.unchanged["jurisdictions"],
        ),
        authorities=HierarchySyncCountsResponse(
            created=summary.created["authorities"],
            updated=summary.updated["authorities"],
            unchanged=summary.unchanged["authorities"],
        ),
        scrape_targets=HierarchySyncCountsResponse(created=0, updated=0, unchanged=0),
    )
