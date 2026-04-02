from typing import Annotated

from fastapi import APIRouter, Depends, status
from sqlalchemy.ext.asyncio import AsyncSession

from platform_control.config import get_settings
from platform_control.database import get_session
from platform_control.schemas.document_events import DocumentLifecycleEventListResponse
from platform_control.schemas.processing_status import ProcessingStatusUpdateListResponse
from platform_control.schemas.run import CreateRunRequest, RunResponse
from platform_control.services.firecrawl_provider import FirecrawlProvider
from platform_control.services.processing_status_service import ProcessingStatusService
from platform_control.services.run_service import RunService

router = APIRouter(prefix="/v1/runs", tags=["runs"])
SessionDep = Annotated[AsyncSession, Depends(get_session)]


def get_firecrawl_provider() -> FirecrawlProvider:
    return FirecrawlProvider(get_settings())


ProviderDep = Annotated[FirecrawlProvider, Depends(get_firecrawl_provider)]


@router.post("", response_model=RunResponse, status_code=status.HTTP_201_CREATED)
async def create_run(
    request: CreateRunRequest,
    session: SessionDep,
    provider: ProviderDep,
) -> RunResponse:
    service = RunService(session, provider)
    return await service.create_run(request)


@router.get("/{run_id}", response_model=RunResponse)
async def get_run(
    run_id: str,
    session: SessionDep,
    provider: ProviderDep,
) -> RunResponse:
    service = RunService(session, provider)
    return await service.get_run(run_id)


@router.get("/{run_id}/processing-status", response_model=ProcessingStatusUpdateListResponse)
async def list_run_processing_status(
    run_id: str,
    session: SessionDep,
) -> ProcessingStatusUpdateListResponse:
    service = ProcessingStatusService(session)
    updates = await service.list_run_processing_status(run_id)
    return ProcessingStatusUpdateListResponse(data=updates)


@router.get("/{run_id}/document-lifecycle", response_model=DocumentLifecycleEventListResponse)
async def list_run_document_lifecycle(
    run_id: str,
    session: SessionDep,
) -> DocumentLifecycleEventListResponse:
    service = ProcessingStatusService(session)
    events = await service.list_run_document_lifecycle(run_id)
    return DocumentLifecycleEventListResponse(data=events)
