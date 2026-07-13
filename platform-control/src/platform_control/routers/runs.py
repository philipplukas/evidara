from typing import Annotated

from fastapi import APIRouter, Depends, Query, status
from sqlalchemy.ext.asyncio import AsyncSession

from platform_control.config import get_settings
from platform_control.database import get_session
from platform_control.domain import RunMode, RunStatus
from platform_control.schemas.document_events import DocumentLifecycleEventListResponse
from platform_control.schemas.lifecycle import RunLifecycleResponse
from platform_control.schemas.processing_status import ProcessingStatusUpdateListResponse
from platform_control.schemas.run import (
    CapturedResourceListResponse,
    CreateRunRequest,
    ProviderJobListResponse,
    RawArtifactListResponse,
    RunListResponse,
    RunPipelineHealthResponse,
    RunPreviewSummaryResponse,
    RunReadinessResponse,
    RunResponse,
)
from platform_control.services.firecrawl_provider import FirecrawlProvider
from platform_control.services.processing_status_service import ProcessingStatusService
from platform_control.services.provider_registry import ProviderRegistry
from platform_control.services.provider_registry_factory import build_provider_registry
from platform_control.services.run_lifecycle_service import RunLifecycleService
from platform_control.services.run_service import RunService

router = APIRouter(prefix="/v1/runs", tags=["runs"])
SessionDep = Annotated[AsyncSession, Depends(get_session)]


def get_firecrawl_provider() -> FirecrawlProvider:
    return FirecrawlProvider(get_settings())


ProviderDep = Annotated[FirecrawlProvider, Depends(get_firecrawl_provider)]


def get_provider_registry(provider: ProviderDep) -> ProviderRegistry:
    registry = build_provider_registry(get_settings())
    # Preserve test override compatibility for get_firecrawl_provider().
    provider_name = getattr(provider, "provider_name", None)
    if isinstance(provider_name, str) and provider_name.strip():
        registry.register(provider)
        return registry

    class _ProviderAdapter:
        provider_name = "firecrawl"
        # Wraps the (live_ready) Firecrawl provider, so it inherits its key.
        live_ready = True

        async def start_run(self, source, source_version, run):
            return await provider.start_run(source, source_version, run)

    registry.register(_ProviderAdapter())
    return registry


@router.get("", response_model=RunListResponse)
async def list_runs(
    session: SessionDep,
    mode: RunMode | None = None,
    status: RunStatus | None = None,
    source_id: str | None = None,
    limit: int = 100,
    offset: int = 0,
) -> RunListResponse:
    service = RunService(session)
    clamped_limit = max(1, min(limit, 500))
    clamped_offset = max(0, offset)
    data, total = await service.list_runs(
        mode=mode,
        status=status,
        source_id=source_id,
        limit=clamped_limit,
        offset=clamped_offset,
    )
    return RunListResponse(data=data, total=total, limit=clamped_limit, offset=clamped_offset)


@router.post("", response_model=RunResponse, status_code=status.HTTP_201_CREATED)
async def create_run(
    request: CreateRunRequest,
    session: SessionDep,
    provider_registry: Annotated[ProviderRegistry, Depends(get_provider_registry)],
) -> RunResponse:
    settings = get_settings()
    service = RunService(
        session,
        provider_registry=provider_registry,
        run_dispatch_backend=settings.run_dispatch_backend,
    )
    return await service.create_run(request)


@router.get("/readiness", response_model=RunReadinessResponse)
async def get_run_readiness(
    source_id: str,
    source_version_id: str,
    session: SessionDep,
    mode: RunMode = RunMode.PREVIEW,
) -> RunReadinessResponse:
    service = RunService(session)
    return await service.get_run_readiness(
        source_id=source_id,
        source_version_id=source_version_id,
        mode=mode,
    )


@router.get("/{run_id}", response_model=RunResponse)
async def get_run(
    run_id: str,
    session: SessionDep,
) -> RunResponse:
    service = RunService(session)
    return await service.get_run(run_id)


@router.get("/{run_id}/captured-resources", response_model=CapturedResourceListResponse)
async def list_run_captured_resources(
    run_id: str,
    session: SessionDep,
    limit: Annotated[int, Query(ge=1, le=500)] = 100,
    offset: Annotated[int, Query(ge=0)] = 0,
) -> CapturedResourceListResponse:
    service = RunService(session)
    return await service.list_captured_resources(run_id, limit=limit, offset=offset)


@router.get("/{run_id}/raw-artifacts", response_model=RawArtifactListResponse)
async def list_run_raw_artifacts(
    run_id: str,
    session: SessionDep,
    limit: Annotated[int, Query(ge=1, le=500)] = 100,
    offset: Annotated[int, Query(ge=0)] = 0,
) -> RawArtifactListResponse:
    service = RunService(session)
    return await service.list_raw_artifacts(run_id, limit=limit, offset=offset)


@router.get("/{run_id}/provider-jobs", response_model=ProviderJobListResponse)
async def list_run_provider_jobs(
    run_id: str,
    session: SessionDep,
    limit: Annotated[int, Query(ge=1, le=500)] = 100,
    offset: Annotated[int, Query(ge=0)] = 0,
) -> ProviderJobListResponse:
    service = RunService(session)
    return await service.list_provider_jobs(run_id, limit=limit, offset=offset)


@router.post("/{run_id}/cancel", response_model=RunResponse)
async def cancel_run(
    run_id: str,
    session: SessionDep,
) -> RunResponse:
    service = RunService(session)
    return await service.cancel_run(run_id)


@router.post("/{run_id}/retry", response_model=RunResponse)
async def retry_run(
    run_id: str,
    session: SessionDep,
) -> RunResponse:
    """Retry a failed or cancelled run. Resets the run to PENDING status."""
    service = RunService(session)
    return await service.retry_run(run_id)


@router.get("/{run_id}/preview-summary", response_model=RunPreviewSummaryResponse)
async def get_run_preview_summary(
    run_id: str,
    session: SessionDep,
) -> RunPreviewSummaryResponse:
    service = RunService(session)
    return await service.get_preview_summary(run_id)


@router.get("/{run_id}/pipeline-health", response_model=RunPipelineHealthResponse)
async def get_run_pipeline_health(
    run_id: str,
    session: SessionDep,
) -> RunPipelineHealthResponse:
    service = RunService(session)
    return await service.get_pipeline_health(run_id)


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


@router.get("/{run_id}/lifecycle", response_model=RunLifecycleResponse)
async def get_run_lifecycle(
    run_id: str,
    session: SessionDep,
) -> RunLifecycleResponse:
    """Aggregated timeline: run events, processing status, and document lifecycle."""
    service = RunLifecycleService(session)
    return await service.get_lifecycle(run_id)
