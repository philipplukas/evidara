"""`GET /v1/acquisition-coverage` — the platform-control half of ADR-0042 §4.

Named `acquisition-coverage`, not `coverage`, because legal-search already serves
`GET /v1/coverage` and the two answer different questions:

    legal-search /v1/coverage         what does the corpus HOLD?      basis: index
    platform-control here             what were we asked to ACQUIRE,  basis:
                                      and did it succeed?             platform_control_runs

An operator who conflates them gets an answer about holdings when they asked about
attempts. ADR-0042 §5 names this deferred item literally — "Acquisition-scope coverage on
platform-control" — and this is it.
"""

from typing import Annotated

from fastapi import APIRouter, Depends, Query
from sqlalchemy.ext.asyncio import AsyncSession

from platform_control.database import get_session
from platform_control.domain import NormLevel
from platform_control.openapi import AGENT_DISCOVERY_TAG
from platform_control.schemas.coverage import AcquisitionCoverageListResponse
from platform_control.services.coverage_service import MAX_PAGE_SIZE, CoverageService

router = APIRouter(prefix="/v1/acquisition-coverage", tags=["acquisition-coverage"])
SessionDep = Annotated[AsyncSession, Depends(get_session)]


@router.get(
    "",
    response_model=AcquisitionCoverageListResponse,
    tags=[AGENT_DISCOVERY_TAG],
    summary="Acquisition coverage per jurisdiction",
    # No `responses=error_responses(...)`: a collection cannot 404, and
    # `test_routes_declare_the_errors_their_handlers_return` asserts exact set equality,
    # so declaring an error this handler cannot return fails as hard as omitting one.
)
async def get_acquisition_coverage(
    session: SessionDep,
    limit: Annotated[int, Query(ge=1, le=MAX_PAGE_SIZE)] = 100,
    offset: Annotated[int, Query(ge=0)] = 0,
    level: Annotated[NormLevel | None, Query()] = None,
) -> AcquisitionCoverageListResponse:
    """Report `expected -> discovered -> acquired -> processed` per jurisdiction.

    `indexed` is absent by design and named in `summary.unmeasured_stages`: it lives in
    legal-search's index, which this service has no dependency on. Reporting it from here
    would be an inference presented as a measurement.
    """
    service = CoverageService(session)
    payload = await service.get_acquisition_coverage(
        limit=limit, offset=offset, level=level.value if level else None
    )
    return AcquisitionCoverageListResponse.model_validate(payload)
