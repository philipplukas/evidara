from typing import Annotated

from fastapi import APIRouter, Depends, Query, status
from sqlalchemy.ext.asyncio import AsyncSession

from platform_control.database import get_session, get_session_maker
from platform_control.schemas.errors import error_responses
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

#: Server-side ceiling on ``limit``, matching ``/v1/sources`` and ``/v1/runs``.
#: The admin's paging loop for reference dropdowns requests exactly this size.
MAX_PAGE_SIZE = 500


@router.get("/jurisdictions", response_model=JurisdictionListResponse)
async def list_jurisdictions(
    session: SessionDep,
    limit: int = 100,
    offset: int = 0,
    q: str | None = None,
) -> JurisdictionListResponse:
    service = ReferenceDataService(session)
    clamped_limit = max(1, min(limit, MAX_PAGE_SIZE))
    clamped_offset = max(0, offset)
    data, total = await service.list_jurisdictions(limit=clamped_limit, offset=clamped_offset, q=q)
    return JurisdictionListResponse(
        data=data, total=total, limit=clamped_limit, offset=clamped_offset
    )


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


@router.patch(
    "/jurisdictions/{jurisdiction_id}",
    response_model=JurisdictionResponse,
    responses=error_responses(404),
)
async def update_jurisdiction(
    jurisdiction_id: str,
    request: UpdateJurisdictionRequest,
    session: SessionDep,
) -> JurisdictionResponse:
    service = ReferenceDataService(session)
    return await service.update_jurisdiction(jurisdiction_id, request)


@router.get("/authorities", response_model=AuthorityListResponse)
async def list_authorities(
    session: SessionDep,
    limit: int = 100,
    offset: int = 0,
    q: str | None = None,
) -> AuthorityListResponse:
    service = ReferenceDataService(session)
    clamped_limit = max(1, min(limit, MAX_PAGE_SIZE))
    clamped_offset = max(0, offset)
    data, total = await service.list_authorities(limit=clamped_limit, offset=clamped_offset, q=q)
    return AuthorityListResponse(data=data, total=total, limit=clamped_limit, offset=clamped_offset)


@router.post(
    "/authorities",
    response_model=AuthorityResponse,
    status_code=status.HTTP_201_CREATED,
    responses=error_responses(404),
)
async def create_authority(
    request: CreateAuthorityRequest,
    session: SessionDep,
) -> AuthorityResponse:
    service = ReferenceDataService(session)
    return await service.create_authority(request)


@router.patch(
    "/authorities/{authority_id}",
    response_model=AuthorityResponse,
    responses=error_responses(404),
)
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
    # Thin shim over ReferenceDataSeeder (issue #312). The legacy
    # HierarchySyncService and its path-based YAMLs are gone; the canonical
    # `seeds/reference/` bundles are the single source of truth.
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
    )
