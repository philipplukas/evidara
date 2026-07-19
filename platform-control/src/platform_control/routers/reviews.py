"""Operator review queue.

Tasks are routed here by the confidence-band policy (see
``docs/runbooks/extraction-review-routing.md``), read by ``platform-control/admin``,
and closed by an operator's decision. The Argilla enqueue/sync endpoints are gone —
ADR-0031.
"""

from __future__ import annotations

from typing import Annotated

from fastapi import APIRouter, Depends, status
from sqlalchemy.ext.asyncio import AsyncSession

from platform_control.database import get_session
from platform_control.schemas.errors import error_responses
from platform_control.schemas.wizard import (
    CreateReviewTaskRequest,
    ReviewDecisionRequest,
    ReviewTaskResponse,
)
from platform_control.services.orchestrator import InMemoryOrchestrator
from platform_control.services.wizard_service import WizardService

router = APIRouter(prefix="/v1/reviews", tags=["reviews"])
SessionDep = Annotated[AsyncSession, Depends(get_session)]


def get_reviews_wizard_service(session: SessionDep) -> WizardService:
    return WizardService(session, InMemoryOrchestrator())


ServiceDep = Annotated[WizardService, Depends(get_reviews_wizard_service)]


@router.post(
    "/tasks",
    response_model=ReviewTaskResponse,
    status_code=status.HTTP_201_CREATED,
    responses=error_responses(404, 409),
)
async def create_review_task(
    request: CreateReviewTaskRequest,
    service: ServiceDep,
) -> ReviewTaskResponse:
    """Enqueue an extraction review task.

    Persisting the task is the enqueue: the queue is the review_tasks table, read by
    platform-control/admin. What lands here is decided by the confidence-band routing
    policy (docs/runbooks/extraction-review-routing.md).
    """
    return await service.create_review_task(request)


@router.get(
    "/tasks/{task_id}",
    response_model=ReviewTaskResponse,
    responses=error_responses(404),
)
async def get_review_task(task_id: str, service: ServiceDep) -> ReviewTaskResponse:
    task = await service.get_review_task(task_id)
    return ReviewTaskResponse.model_validate(task)


@router.post(
    "/tasks/{task_id}/decision",
    response_model=ReviewTaskResponse,
    responses=error_responses(404, 409),
)
async def record_review_decision(
    task_id: str,
    request: ReviewDecisionRequest,
    service: ServiceDep,
) -> ReviewTaskResponse:
    """Close a review task with an operator's verdict.

    Replaces ``POST /v1/reviews/sync-from-argilla``: the decision is pushed by the
    reviewer instead of polled out of an annotation tool.
    """
    return await service.record_review_decision(task_id, request)
