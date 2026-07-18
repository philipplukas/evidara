from typing import Annotated

from fastapi import APIRouter, Depends, status
from sqlalchemy.ext.asyncio import AsyncSession

from platform_control.auth import Principal, get_current_principal
from platform_control.database import get_session
from platform_control.openapi import AGENT_DISCOVERY_TAG
from platform_control.schemas.source import (
    BlueprintTemplateEnablementRequest,
    BlueprintTemplateEnablementResponse,
    CreateSourceRequest,
    CreateSourceVersionRequest,
    CreateSourceWithVersionRequest,
    CreateSourceWithVersionResponse,
    SourceBlueprintPreviewRequest,
    SourceBlueprintPreviewResponse,
    SourceBlueprintTemplateListResponse,
    SourceListResponse,
    SourceResponse,
    SourceVersionListResponse,
    SourceVersionResponse,
)
from platform_control.services.blueprint_enablement import BlueprintEnablementService
from platform_control.services.source_service import SourceService

router = APIRouter(prefix="/v1/sources", tags=["sources", "source-versions"])
SessionDep = Annotated[AsyncSession, Depends(get_session)]
PrincipalDep = Annotated[Principal, Depends(get_current_principal)]


@router.get("", response_model=SourceListResponse, tags=[AGENT_DISCOVERY_TAG])
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


@router.post(
    "/with-version",
    response_model=CreateSourceWithVersionResponse,
    status_code=status.HTTP_201_CREATED,
)
async def create_source_with_initial_version(
    request: CreateSourceWithVersionRequest,
    session: SessionDep,
) -> CreateSourceWithVersionResponse:
    service = SourceService(session)
    source, source_version = await service.create_source_with_initial_version(request)
    return CreateSourceWithVersionResponse(source=source, source_version=source_version)


@router.post("/blueprint-preview", response_model=SourceBlueprintPreviewResponse)
async def preview_source_blueprint(
    request: SourceBlueprintPreviewRequest,
    session: SessionDep,
) -> SourceBlueprintPreviewResponse:
    service = SourceService(session)
    acquisition_spec = await service.preview_source_blueprint(request)
    lock = await service.describe_blueprint_lock(
        request.overlay_id,
        request.provider_template_id,
        acquisition_spec.provider,
    )
    return SourceBlueprintPreviewResponse(
        overlay_id=request.overlay_id,
        provider_template_id=request.provider_template_id,
        acquisition_spec=acquisition_spec,
        enabled=bool(lock["enabled"]),
        live_ready=bool(lock["live_ready"]),
        launchable=bool(lock["launchable"]),
        notes=list(lock["notes"]),
    )


@router.get("/blueprint-templates", response_model=SourceBlueprintTemplateListResponse)
async def list_source_blueprint_templates(
    session: SessionDep,
) -> SourceBlueprintTemplateListResponse:
    service = SourceService(session)
    return SourceBlueprintTemplateListResponse(data=await service.list_source_blueprint_templates())


@router.put(
    "/blueprint-templates/{overlay_id}/{provider_template_id}/enablement",
    response_model=BlueprintTemplateEnablementResponse,
)
async def set_blueprint_template_enablement(
    overlay_id: str,
    provider_template_id: str,
    request: BlueprintTemplateEnablementRequest,
    session: SessionDep,
    principal: PrincipalDep,
) -> BlueprintTemplateEnablementResponse:
    """Flip the operator-reachable ADR-0030 config key for one template (#632).

    This is the key an operator turns after capturing acceptance-run evidence —
    reachable over the API, with an audit trail (who/when/why), no repo edit and
    no deploy. The code key (`live_ready`) is unaffected: a run at a scaffold
    provider still refuses even once this is enabled.
    """
    service = BlueprintEnablementService(session)
    state = await service.set_enabled(
        overlay_id,
        provider_template_id,
        enabled=request.enabled,
        note=request.note,
        actor=principal.operator_id,
    )
    await session.commit()
    return BlueprintTemplateEnablementResponse(
        overlay_id=state.overlay_id,
        provider_template_id=state.provider_template_id,
        enabled=state.enabled,
        default_enabled=state.default_enabled,
        source=state.source,
        note=state.note,
        updated_by=state.updated_by,
        updated_at=state.updated_at,
    )


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
