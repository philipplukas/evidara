from typing import Annotated

from fastapi import APIRouter, Depends, Request, status
from fastapi.responses import JSONResponse
from sqlalchemy.ext.asyncio import AsyncSession

from acquisition_core.providers import AcquisitionReadiness
from platform_control.auth import Principal, get_current_principal
from platform_control.database import get_session
from platform_control.openapi import AGENT_DISCOVERY_TAG
from platform_control.schemas.errors import error_responses
from platform_control.schemas.source import (
    BlueprintTemplateAcceptanceVerdict,
    BlueprintTemplateEnablementRefusal,
    BlueprintTemplateEnablementRefusedResponse,
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
from platform_control.services.blueprint_enablement import BlueprintEnablementGuard
from platform_control.services.blueprint_enablement_guard import AcceptanceVerdict, Refusal
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


@router.post(
    "",
    response_model=SourceResponse,
    status_code=status.HTTP_201_CREATED,
    responses=error_responses(404, 409),
)
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
    responses=error_responses(404, 409),
)
async def create_source_with_initial_version(
    request: CreateSourceWithVersionRequest,
    session: SessionDep,
) -> CreateSourceWithVersionResponse:
    service = SourceService(session)
    source, source_version = await service.create_source_with_initial_version(request)
    return CreateSourceWithVersionResponse(source=source, source_version=source_version)


@router.post(
    "/blueprint-preview",
    response_model=SourceBlueprintPreviewResponse,
    responses=error_responses(404, 409),
)
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
        acquisition_readiness=AcquisitionReadiness(lock["acquisition_readiness"]),
        launchable=bool(lock["launchable"]),
        notes=list(lock["notes"]),
        plan_notes=service.describe_blueprint_plan_notes(acquisition_spec),
    )


@router.get("/blueprint-templates", response_model=SourceBlueprintTemplateListResponse)
async def list_source_blueprint_templates(
    session: SessionDep,
) -> SourceBlueprintTemplateListResponse:
    service = SourceService(session)
    return SourceBlueprintTemplateListResponse(data=await service.list_source_blueprint_templates())


def _refusal_models(
    refusals: list[Refusal],
) -> list[BlueprintTemplateEnablementRefusal]:
    return [
        BlueprintTemplateEnablementRefusal(code=item.code, detail=item.detail) for item in refusals
    ]


def _acceptance_verdict_model(
    verdict: AcceptanceVerdict | None,
) -> BlueprintTemplateAcceptanceVerdict | None:
    if verdict is None:
        return None
    return BlueprintTemplateAcceptanceVerdict(
        is_acceptance_evidence=verdict.is_acceptance_evidence,
        refusals=_refusal_models(verdict.refusals),
        run_id=verdict.run_id,
        mode=verdict.mode,
        execution_mode=verdict.execution_mode,
        captured_resources_count=verdict.captured_resources_count,
    )


@router.put(
    "/blueprint-templates/{overlay_id}/{provider_template_id}/enablement",
    response_model=BlueprintTemplateEnablementResponse,
    responses={
        **error_responses(404),
        status.HTTP_409_CONFLICT: {
            "model": BlueprintTemplateEnablementRefusedResponse,
            "description": (
                "The ADR-0030 guard refused to move the config key. `refusals[].code` "
                "names why, in the same vocabulary `evidara workflow coverage enable` "
                "reports. `write_attempted: false` means nothing was written."
            ),
        },
    },
)
async def set_blueprint_template_enablement(
    overlay_id: str,
    provider_template_id: str,
    request: BlueprintTemplateEnablementRequest,
    session: SessionDep,
    principal: PrincipalDep,
    http_request: Request,
) -> BlueprintTemplateEnablementResponse | JSONResponse:
    """Flip the operator-reachable ADR-0030 config key for one template (#632, #854).

    This is the key an operator turns after capturing acceptance-run evidence —
    reachable over the API, with an audit trail (who/when/why), no repo edit and
    no deploy. The code key (`live_ready`) is unaffected: a run at a scaffold
    provider still refuses even once this is enabled.

    **The guard is here, not in the clients.** Enabling requires a cited
    `evidence_run_id` whose run survives the ADR-0030 acceptance verdict and binds to
    *this* template — not merely to its provider, which for `lexfind` would be 26
    cantons plus Bund off one canton's run (#846). Reopening a key an operator
    deliberately shut, and arming the config key ahead of the code key, each need their
    own acknowledgement. Refusals come back as **409** with machine-readable codes and
    nothing written; a 200 additionally asserts `applied`, which is a genuine read-back
    rather than the status code (#631, #713).
    """
    guard = BlueprintEnablementGuard(session)
    outcome = await guard.flip(
        overlay_id,
        provider_template_id,
        enabled=request.enabled,
        note=request.note,
        evidence_run_id=request.evidence_run_id,
        reopen_operator_kill_switch=request.reopen_operator_kill_switch,
        acknowledge_provider_below_live=request.acknowledge_provider_below_live,
        actor=principal.operator_id,
    )

    if outcome.refused or outcome.state is None:
        refused = BlueprintTemplateEnablementRefusedResponse(
            detail=outcome.refusals[0].detail if outcome.refusals else "Refused.",
            correlation_id=getattr(http_request.state, "correlation_id", None) or None,
            overlay_id=overlay_id,
            provider_template_id=provider_template_id,
            refusals=_refusal_models(outcome.refusals),
            needs_human=True,
            write_attempted=outcome.write_attempted,
            evidence_run_id=outcome.evidence_run_id,
            evidence_binding=outcome.evidence_binding,
            acceptance_verdict=_acceptance_verdict_model(outcome.acceptance_verdict),
        )
        return JSONResponse(
            status_code=status.HTTP_409_CONFLICT,
            content=refused.model_dump(mode="json"),
        )

    state = outcome.state
    return BlueprintTemplateEnablementResponse(
        overlay_id=state.overlay_id,
        provider_template_id=state.provider_template_id,
        enabled=state.enabled,
        default_enabled=state.default_enabled,
        source=state.source,
        note=state.note,
        updated_by=state.updated_by,
        updated_at=state.updated_at,
        applied=outcome.applied,
        needs_human=outcome.needs_human,
        needs_human_reasons=outcome.needs_human_reasons,
        evidence_run_id=outcome.evidence_run_id,
        evidence_binding=outcome.evidence_binding,
        acceptance_verdict=_acceptance_verdict_model(outcome.acceptance_verdict),
    )


@router.get("/{source_id}", response_model=SourceResponse, responses=error_responses(404))
async def get_source(
    source_id: str,
    session: SessionDep,
) -> SourceResponse:
    service = SourceService(session)
    return await service.get_source(source_id)


@router.get(
    "/{source_id}/versions",
    response_model=SourceVersionListResponse,
    responses=error_responses(404),
)
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
    responses=error_responses(404, 409),
)
async def create_source_version(
    source_id: str,
    request: CreateSourceVersionRequest,
    session: SessionDep,
) -> SourceVersionResponse:
    service = SourceService(session)
    return await service.create_source_version(source_id, request)
