"""Corrections router.

Combines:

* Operator queue read endpoint (``GET /v1/corrections/queue``) from #421.
* Targeted-rescore action endpoint (``POST /v1/corrections/{id}/rescore``) from #427.

# CONTRACT-PENDING (#427): the rescore endpoint is not yet reflected in
# ``contracts/api/platform-control.openapi.yaml``. The shape implemented:
#
#   POST /v1/corrections/{correction_id}/rescore
#     requestBody: { rationale?: string<=2000, dry_run?: bool }
#     responses:
#       202: { rescore_correction_id: string,
#              workflow_id: string,
#              run_id: string|null }
#       404: standard NotFound
#       422: standard ValidationError
"""

from __future__ import annotations

from datetime import date
from typing import Annotated

from fastapi import APIRouter, Depends, Query, status
from sqlalchemy.ext.asyncio import AsyncSession

from platform_control.config import Settings, get_settings
from platform_control.database import get_session
from platform_control.domain import (
    CorrectionStatus,
    CorrectionTargetEntityType,
    CorrectionType,
)
from platform_control.schemas.correction import (
    CorrectionListResponse,
    CorrectionMetricsResponse,
    CorrectionResponse,
    RescoreRequest,
    RescoreResponse,
)
from platform_control.services.correction_service import (
    CorrectionService,
    RescoreOrchestrator,
)
from platform_control.services.orchestrator import (
    InMemoryOrchestrator,
    TemporalOrchestrator,
)

router = APIRouter(prefix="/v1", tags=["corrections"])
SessionDep = Annotated[AsyncSession, Depends(get_session)]


def get_rescore_orchestrator(
    settings: Annotated[Settings, Depends(get_settings)],
) -> RescoreOrchestrator:
    """Resolve the rescore orchestrator backend.

    Mirrors the wizard backend selector — ``temporal`` boots a
    ``TemporalOrchestrator`` and any other value (default ``in_memory``)
    falls back to the no-op stub. Tests override this dependency directly.
    """
    if settings.wizard_orchestrator_backend == "temporal":
        return TemporalOrchestrator(
            namespace=settings.temporal_namespace,
            task_queue=settings.temporal_task_queue,
            target=settings.temporal_target,
        )
    return InMemoryOrchestrator()


def get_correction_service(
    session: SessionDep,
    orchestrator: Annotated[RescoreOrchestrator, Depends(get_rescore_orchestrator)],
) -> CorrectionService:
    return CorrectionService(session, rescore_orchestrator=orchestrator)


@router.get(
    "/corrections/queue",
    response_model=CorrectionListResponse,
)
async def list_correction_queue(
    session: SessionDep,
    target_entity_type: Annotated[CorrectionTargetEntityType | None, Query()] = None,
    correction_type: Annotated[CorrectionType | None, Query()] = None,
    status_: Annotated[CorrectionStatus, Query(alias="status")] = CorrectionStatus.PENDING,
    limit: Annotated[int, Query(ge=1, le=500)] = 50,
) -> CorrectionListResponse:
    service = CorrectionService(session)
    rows = await service.list_queue(
        target_entity_type=target_entity_type,
        correction_type=correction_type,
        status=status_,
        limit=limit,
    )
    return CorrectionListResponse(data=[CorrectionResponse.model_validate(row) for row in rows])


@router.post(
    "/corrections/{correction_id}/rescore",
    response_model=RescoreResponse,
    status_code=status.HTTP_202_ACCEPTED,
)
async def request_rescore(
    correction_id: str,
    payload: RescoreRequest,
    service: Annotated[CorrectionService, Depends(get_correction_service)],
) -> RescoreResponse:
    """Schedule a targeted rescore from a parent correction.

    Returns 202 Accepted with the new ``rescore_correction_id`` plus the
    Temporal workflow / run identifiers. Idempotent on the
    ``(correction_id, target_entity_id)`` pair.
    """
    return await service.request_rescore(correction_id, payload)


@router.get(
    "/corrections/metrics",
    response_model=CorrectionMetricsResponse,
)
async def get_correction_metrics(
    session: SessionDep,
    since: Annotated[
        date | None,
        Query(
            description=(
                "ISO date (YYYY-MM-DD). Defaults to 12 weeks before now. "
                "Snapped to the Monday of the containing ISO week."
            )
        ),
    ] = None,
) -> CorrectionMetricsResponse:
    """Aggregate weekly correction metrics for the dashboard widget (#432).

    Returns one bucket per ISO week between ``since`` and the current week,
    inclusive of both ends. Buckets are pre-seeded so empty weeks render as
    zeroed cards rather than gaps.
    """
    service = CorrectionService(session)
    return await service.get_metrics(since=since)
