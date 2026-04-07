from __future__ import annotations

from typing import Annotated

from fastapi import APIRouter, Depends, status
from sqlalchemy.ext.asyncio import AsyncSession

from platform_control.config import get_settings
from platform_control.database import get_session
from platform_control.schemas.wizard import (
    CreateWizardProjectRequest,
    StartWizardPilotRunRequest,
    UpdateWizardDiscoveryPlanRequest,
    UpdateWizardScopeRequest,
    WizardProjectResponse,
    WizardRunDecisionRequest,
    WizardRunHealth,
    WizardRunProgress,
    WizardRunQuality,
    WizardRunStatusResponse,
)
from platform_control.services.orchestrator import (
    InMemoryOrchestrator,
    Orchestrator,
    TemporalOrchestrator,
)
from platform_control.services.wizard_service import WizardService

router = APIRouter(prefix="/v1/wizard", tags=["wizard"])
SessionDep = Annotated[AsyncSession, Depends(get_session)]


def get_orchestrator() -> Orchestrator:
    settings = get_settings()
    if settings.wizard_orchestrator_backend == "temporal":
        return TemporalOrchestrator(
            namespace=settings.temporal_namespace,
            task_queue=settings.temporal_task_queue,
            target=settings.temporal_target,
        )
    return InMemoryOrchestrator()


def _to_status_response(run) -> WizardRunStatusResponse:
    progress = run.progress or {}
    quality = run.quality or {}
    health = run.health or {}
    return WizardRunStatusResponse(
        wizard_run_id=run.wizard_run_id,
        wizard_project_id=run.wizard_project_id,
        workflow_id=run.workflow_id,
        state=run.state,
        state_entered_at=run.state_entered_at,
        progress=WizardRunProgress(
            total_nodes=int(progress.get("total_nodes", 0)),
            processed_nodes=int(progress.get("processed_nodes", 0)),
            routed_to_review=int(progress.get("routed_to_review", 0)),
            accepted_records=int(progress.get("accepted_records", 0)),
        ),
        quality=WizardRunQuality(
            confidence_distribution=dict(quality.get("confidence_distribution", {})),
            conflict_count=int(quality.get("conflict_count", 0)),
            review_backlog=int(quality.get("review_backlog", 0)),
        ),
        health=WizardRunHealth(
            retry_counters=dict(health.get("retry_counters", {})),
            last_errors=list(health.get("last_errors", [])),
            next_retry_window=health.get("next_retry_window"),
        ),
        failure_reason=run.failure_reason,
        created_at=run.created_at,
        updated_at=run.updated_at,
    )


@router.post("/projects", response_model=WizardProjectResponse, status_code=status.HTTP_201_CREATED)
async def create_project(
    request: CreateWizardProjectRequest,
    session: SessionDep,
    orchestrator: Annotated[Orchestrator, Depends(get_orchestrator)],
) -> WizardProjectResponse:
    service = WizardService(session, orchestrator)
    project = await service.create_project(request)
    return WizardProjectResponse.model_validate(project)


@router.get("/projects/{project_id}", response_model=WizardProjectResponse)
async def get_project(
    project_id: str,
    session: SessionDep,
    orchestrator: Annotated[Orchestrator, Depends(get_orchestrator)],
) -> WizardProjectResponse:
    service = WizardService(session, orchestrator)
    project = await service.get_project(project_id)
    return WizardProjectResponse.model_validate(project)


@router.post("/projects/{project_id}/scope", response_model=WizardProjectResponse)
async def save_scope(
    project_id: str,
    request: UpdateWizardScopeRequest,
    session: SessionDep,
    orchestrator: Annotated[Orchestrator, Depends(get_orchestrator)],
) -> WizardProjectResponse:
    service = WizardService(session, orchestrator)
    project = await service.update_scope(project_id, request.scope)
    return WizardProjectResponse.model_validate(project)


@router.post("/projects/{project_id}/discovery-plan", response_model=WizardProjectResponse)
async def save_discovery_plan(
    project_id: str,
    request: UpdateWizardDiscoveryPlanRequest,
    session: SessionDep,
    orchestrator: Annotated[Orchestrator, Depends(get_orchestrator)],
) -> WizardProjectResponse:
    service = WizardService(session, orchestrator)
    project = await service.update_discovery_plan(project_id, request.discovery_plan)
    return WizardProjectResponse.model_validate(project)


@router.post("/projects/{project_id}/pilot-run", response_model=WizardRunStatusResponse)
async def start_pilot_run(
    project_id: str,
    request: StartWizardPilotRunRequest,
    session: SessionDep,
    orchestrator: Annotated[Orchestrator, Depends(get_orchestrator)],
) -> WizardRunStatusResponse:
    service = WizardService(session, orchestrator)
    run = await service.start_pilot_run(project_id, request.sample_limit)
    return _to_status_response(run)


@router.get("/runs/{run_id}", response_model=WizardRunStatusResponse)
async def get_run(
    run_id: str,
    session: SessionDep,
    orchestrator: Annotated[Orchestrator, Depends(get_orchestrator)],
) -> WizardRunStatusResponse:
    service = WizardService(session, orchestrator)
    run = await service.get_run(run_id)
    return _to_status_response(run)


@router.post("/runs/{run_id}/approve", response_model=WizardRunStatusResponse)
async def approve_run(
    run_id: str,
    request: WizardRunDecisionRequest,
    session: SessionDep,
    orchestrator: Annotated[Orchestrator, Depends(get_orchestrator)],
) -> WizardRunStatusResponse:
    service = WizardService(session, orchestrator)
    run = await service.approve_run(run_id, reason=request.reason)
    return _to_status_response(run)


@router.post("/runs/{run_id}/reject", response_model=WizardRunStatusResponse)
async def reject_run(
    run_id: str,
    request: WizardRunDecisionRequest,
    session: SessionDep,
    orchestrator: Annotated[Orchestrator, Depends(get_orchestrator)],
) -> WizardRunStatusResponse:
    service = WizardService(session, orchestrator)
    run = await service.reject_run(run_id, reason=request.reason)
    return _to_status_response(run)
