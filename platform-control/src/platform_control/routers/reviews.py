from __future__ import annotations

from typing import Annotated

from fastapi import APIRouter, Depends, status
from sqlalchemy.ext.asyncio import AsyncSession

from platform_control.config import get_settings
from platform_control.database import get_session
from platform_control.schemas.wizard import (
    ArgillaReviewSyncRequest,
    ArgillaReviewSyncResponse,
    CreateReviewTaskRequest,
    CreateReviewTaskResponse,
    ReviewTaskResponse,
)
from platform_control.services.argilla_enqueue_service import ArgillaEnqueueService
from platform_control.services.orchestrator import InMemoryOrchestrator
from platform_control.services.wizard_service import WizardService

router = APIRouter(prefix="/v1/reviews", tags=["reviews"])
SessionDep = Annotated[AsyncSession, Depends(get_session)]


def get_argilla_enqueue_service() -> ArgillaEnqueueService:
    return ArgillaEnqueueService(get_settings())


def get_reviews_wizard_service(
    session: SessionDep,
    argilla: Annotated[ArgillaEnqueueService, Depends(get_argilla_enqueue_service)],
) -> WizardService:
    return WizardService(session, InMemoryOrchestrator(), argilla_enqueue=argilla)


@router.post("/sync-from-argilla", response_model=ArgillaReviewSyncResponse)
async def sync_from_argilla(
    payload: ArgillaReviewSyncRequest,
    session: SessionDep,
) -> ArgillaReviewSyncResponse:
    service = WizardService(session, InMemoryOrchestrator())
    return await service.sync_reviews_from_argilla(payload)


@router.post(
    "/tasks",
    response_model=CreateReviewTaskResponse,
    status_code=status.HTTP_201_CREATED,
)
async def create_review_task(
    request: CreateReviewTaskRequest,
    service: Annotated[WizardService, Depends(get_reviews_wizard_service)],
) -> CreateReviewTaskResponse:
    return await service.create_review_task(request)


@router.get("/tasks/{task_id}", response_model=ReviewTaskResponse)
async def get_review_task(
    task_id: str,
    session: SessionDep,
) -> ReviewTaskResponse:
    service = WizardService(session, InMemoryOrchestrator())
    task = await service.get_review_task(task_id)
    return ReviewTaskResponse.model_validate(task)
