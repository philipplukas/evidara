"""HTTP surface for corrections (PR #434 frozen).

The four endpoints below are pinned by `contracts/api/platform-control.openapi.yaml`
0.5.0 (`createCorrection`, `listCorrections`, `getCorrection`,
`updateCorrectionStatus`).

Operator identity is now sourced from the auth-resolved
:class:`Principal` (M11/B1, #452). The legacy ``X-Operator-Id`` header
read is gone; any caller still passing it is silently ignored.
"""

from __future__ import annotations

from typing import Annotated

from fastapi import APIRouter, Depends, Query, status
from pydantic import BaseModel, Field
from sqlalchemy.ext.asyncio import AsyncSession

from platform_control.auth import Principal, get_current_principal
from platform_control.config import get_settings
from platform_control.database import get_session
from platform_control.schemas.correction import (
    CorrectionListResponse,
    CorrectionMetricsResponse,
    CorrectionResponse,
    CorrectionStatus,
    CorrectionType,
    CreateCorrectionRequest,
    TargetEntityType,
    UpdateCorrectionStatusRequest,
)
from platform_control.services.correction_service import CorrectionService
from platform_control.services.rescore_scheduler import (
    RescoreScheduler,
    TemporalRescoreScheduler,
)

router = APIRouter(prefix="/v1", tags=["corrections"])
SessionDep = Annotated[AsyncSession, Depends(get_session)]
PrincipalDep = Annotated[Principal, Depends(get_current_principal)]


_OPERATOR_ID_PATTERN = r"^op_[a-z0-9]+$"


@router.post(
    "/corrections",
    response_model=CorrectionResponse,
    status_code=status.HTTP_201_CREATED,
)
async def create_correction(
    request: CreateCorrectionRequest,
    session: SessionDep,
    principal: PrincipalDep,
) -> CorrectionResponse:
    service = CorrectionService(session)
    row = await service.create(request, operator_id=principal.operator_id)
    return CorrectionResponse.model_validate(row, from_attributes=True)


@router.get(
    "/corrections",
    response_model=CorrectionListResponse,
)
async def list_corrections(
    session: SessionDep,
    target_entity_type: Annotated[TargetEntityType | None, Query()] = None,
    target_entity_id: Annotated[str | None, Query(min_length=1)] = None,
    operator_id: Annotated[str | None, Query(pattern=_OPERATOR_ID_PATTERN)] = None,
    correction_status: Annotated[CorrectionStatus | None, Query(alias="status")] = None,
    correction_type: Annotated[CorrectionType | None, Query()] = None,
    limit: Annotated[int, Query(ge=1, le=500)] = 100,
    offset: Annotated[int, Query(ge=0)] = 0,
) -> CorrectionListResponse:
    service = CorrectionService(session)
    rows, total = await service.list(
        target_entity_type=target_entity_type,
        target_entity_id=target_entity_id,
        operator_id=operator_id,
        status=correction_status,
        correction_type=correction_type,
        limit=limit,
        offset=offset,
    )
    return CorrectionListResponse(
        data=[CorrectionResponse.model_validate(row, from_attributes=True) for row in rows],
        total=total,
        limit=limit,
        offset=offset,
    )


@router.get(
    "/corrections/metrics",
    response_model=CorrectionMetricsResponse,
)
async def get_correction_metrics(
    session: SessionDep,
    window_weeks: Annotated[int, Query(ge=1, le=52)] = 8,
    operator_throughput_window_days: Annotated[int, Query(ge=1, le=365)] = 30,
    operator_throughput_top_n: Annotated[int, Query(ge=1, le=100)] = 10,
) -> CorrectionMetricsResponse:
    """Aggregate read model for the admin dashboard (#432).

    Computed entirely from the corrections audit log — no new
    telemetry store. The route MUST sit above
    `/corrections/{correction_id}` so FastAPI's path-matching doesn't
    treat `metrics` as a correction ID.
    """

    service = CorrectionService(session)
    payload = await service.get_metrics(
        window_weeks=window_weeks,
        operator_throughput_window_days=operator_throughput_window_days,
        operator_throughput_top_n=operator_throughput_top_n,
    )
    return CorrectionMetricsResponse.model_validate(payload)


@router.get(
    "/corrections/{correction_id}",
    response_model=CorrectionResponse,
)
async def get_correction(
    correction_id: str,
    session: SessionDep,
) -> CorrectionResponse:
    service = CorrectionService(session)
    row = await service.get(correction_id)
    return CorrectionResponse.model_validate(row, from_attributes=True)


@router.patch(
    "/corrections/{correction_id}",
    response_model=CorrectionResponse,
)
async def update_correction_status(
    correction_id: str,
    request: UpdateCorrectionStatusRequest,
    session: SessionDep,
) -> CorrectionResponse:
    service = CorrectionService(session)
    row = await service.update_status(correction_id, request)
    return CorrectionResponse.model_validate(row, from_attributes=True)


# ─── Rescore-from-correction (#427) ───────────────────────────────────────────


class RescoreTriggerResponse(BaseModel):
    """Acknowledgement payload for `POST /v1/corrections/{id}/rescore`."""

    correction_id: str
    workflow_id: str = Field(min_length=1)
    already_running: bool
    triggered_at: str | None = None


def _default_rescore_scheduler() -> RescoreScheduler:
    """Production scheduler — connects to Temporal lazily on first call.

    Tests override this dependency via `app.dependency_overrides[
    _default_rescore_scheduler] = lambda: InMemoryRescoreScheduler()`.
    """

    settings = get_settings()
    return TemporalRescoreScheduler(
        namespace=settings.temporal_namespace,
        task_queue=settings.temporal_task_queue,
        target=settings.temporal_target,
    )


RescoreSchedulerDep = Annotated[RescoreScheduler, Depends(_default_rescore_scheduler)]


@router.post(
    "/corrections/{correction_id}/rescore",
    response_model=RescoreTriggerResponse,
    status_code=status.HTTP_202_ACCEPTED,
)
async def trigger_rescore_from_correction(
    correction_id: str,
    session: SessionDep,
    scheduler: RescoreSchedulerDep,
) -> RescoreTriggerResponse:
    """Trigger the rescore-from-correction Temporal workflow (#427).

    Idempotent: re-firing on a correction that has already been
    triggered returns the existing workflow handle and `already_running=True`.
    The endpoint validates that the correction is `rescore_request` and
    in `pending` or `applied` status; non-rescore corrections or
    terminal-state ones return 409 via `ConflictError`.

    Note: this is acknowledgement only — the actual re-extraction runs
    asynchronously via the Temporal workflow. Outcomes
    (`changed`/`unchanged`/`failed`, `resulting_run_id`) are written
    back to the correction's `payload` by
    `RescoreFromCorrectionActivities.run_targeted_rescore`. Operators
    poll `GET /v1/corrections/{correction_id}` to follow the run.
    """

    service = CorrectionService(session)
    payload = await service.trigger_rescore(correction_id, scheduler=scheduler)
    return RescoreTriggerResponse(**payload)
