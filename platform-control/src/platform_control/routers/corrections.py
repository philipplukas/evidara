"""HTTP surface for corrections (PR #434 frozen).

The four endpoints below are pinned by `contracts/api/platform-control.openapi.yaml`
0.5.0 (`createCorrection`, `listCorrections`, `getCorrection`,
`updateCorrectionStatus`).

Operator identity is sourced from an `X-Operator-Id` header for now —
the `require_control_plane_operator` auth dependency confirms the
caller is an authenticated operator but doesn't yet surface a
principal-mapped operator_id. When an authenticated operator-id
mapping lands (follow-up of #421), the header fallback can be removed.
"""

from __future__ import annotations

from typing import Annotated

from fastapi import APIRouter, Depends, Header, Query, status
from sqlalchemy.ext.asyncio import AsyncSession

from platform_control.database import get_session
from platform_control.errors import ConflictError
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

router = APIRouter(prefix="/v1", tags=["corrections"])
SessionDep = Annotated[AsyncSession, Depends(get_session)]


_DEFAULT_OPERATOR_ID = "op_unknown00000000000000000"
_OPERATOR_ID_PATTERN = r"^op_[a-z0-9]+$"


def _operator_id_from_header(
    x_operator_id: Annotated[str | None, Header(alias="X-Operator-Id")] = None,
) -> str:
    """Resolve `operator_id` from the `X-Operator-Id` header.

    Falls back to `op_unknown…` when the caller doesn't supply one — the
    pre-#421 admin tooling doesn't pass this header yet, and we don't want
    to fail-closed before operator identity is wired into the auth layer.
    Once that wiring lands, drop the fallback and require the header.
    """
    import re

    if x_operator_id is None:
        return _DEFAULT_OPERATOR_ID
    if not re.match(_OPERATOR_ID_PATTERN, x_operator_id):
        raise ConflictError(
            f"X-Operator-Id {x_operator_id!r} does not match {_OPERATOR_ID_PATTERN}."
        )
    return x_operator_id


OperatorIdDep = Annotated[str, Depends(_operator_id_from_header)]


@router.post(
    "/corrections",
    response_model=CorrectionResponse,
    status_code=status.HTTP_201_CREATED,
)
async def create_correction(
    request: CreateCorrectionRequest,
    session: SessionDep,
    operator_id: OperatorIdDep,
) -> CorrectionResponse:
    service = CorrectionService(session)
    row = await service.create(request, operator_id=operator_id)
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
