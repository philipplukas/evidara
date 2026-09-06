from fastapi import APIRouter, Response
from fastapi.responses import JSONResponse
from sqlalchemy import func, select, text

from platform_control.build_info import get_build_info
from platform_control.config import get_settings
from platform_control.database import get_session_maker
from platform_control.models.run import Run
from platform_control.models.source import Source
from platform_control.observability.metrics import CONTENT_TYPE_LATEST, render_latest
from platform_control.schema_revision import SchemaRevisionStatus, read_schema_revision
from platform_control.schemas.health import DependencyCheck, HealthResponse, ReadinessResponse

router = APIRouter(tags=["health"])


@router.get("/health", response_model=HealthResponse)
async def get_health() -> HealthResponse:
    settings = get_settings()
    return HealthResponse(
        status="ok",
        service=settings.app_name,
        build=get_build_info(),
    )


@router.get("/metrics", include_in_schema=False)
async def get_metrics() -> Response:
    """Prometheus scrape endpoint (ADR-0032).

    Lives on the unauthenticated health router on purpose: the port is cluster-internal
    (no Ingress route reaches it) and the scraper carries no operator API key.
    """
    return Response(content=render_latest(), media_type=CONTENT_TYPE_LATEST)


@router.get(
    "/ready",
    response_model=ReadinessResponse,
    responses={
        503: {
            "model": ReadinessResponse,
            "description": (
                "At least one dependency check failed. The body is the same readiness "
                "report as the 200, with `status: degraded`."
            ),
        }
    },
)
async def get_readiness() -> JSONResponse:
    settings = get_settings()
    session_maker = get_session_maker()
    checks: dict[str, DependencyCheck] = {}

    try:
        async with session_maker() as session:
            await session.execute(text("SELECT 1"))
            checks["database"] = DependencyCheck(status="ok")

            # Reachable is not the same as usable. A pod whose code expects a
            # newer schema than the database has will pass `SELECT 1`, serve
            # traffic, and fail only at the statement that needs the new column
            # or enum label — which is how a 2026-09-06 pin bump rolled an API
            # ahead of its migration with every signal reading green.
            revision = await read_schema_revision(session)
            checks["schema_revision"] = DependencyCheck(
                # UNKNOWN is reported, never asserted: it is the normal answer
                # under `create_all`, and degrading on it would make every test
                # suite unready. Only a real MISMATCH takes the pod out of
                # service.
                status="error" if revision.status is SchemaRevisionStatus.MISMATCH else "ok",
                detail=revision.detail,
            )
    except Exception as error:  # pragma: no cover - defensive runtime safety
        checks["database"] = DependencyCheck(
            status="error",
            detail=f"database_unreachable: {error}",
        )

    status = "ok" if all(check.status == "ok" for check in checks.values()) else "degraded"
    payload = ReadinessResponse(status=status, service=settings.app_name, checks=checks)
    http_status = 200 if status == "ok" else 503
    return JSONResponse(status_code=http_status, content=payload.model_dump())


@router.get("/stats")
async def get_stats() -> dict:
    session_maker = get_session_maker()
    async with session_maker() as session:
        source_count = (await session.execute(select(func.count(Source.source_id)))).scalar() or 0

        run_rows = await session.execute(
            select(Run.status, func.count(Run.run_id)).group_by(Run.status)
        )
        run_by_status = {row[0]: row[1] for row in run_rows}
        total_runs = sum(run_by_status.values())

        artifact_result = await session.execute(select(func.sum(Run.artifacts_count)))
        total_artifacts = artifact_result.scalar() or 0

        recent_rows = await session.execute(
            select(
                Run.run_id,
                Run.status,
                Run.artifacts_count,
                Run.created_at,
                Run.started_at,
                Run.completed_at,
            )
            .order_by(Run.created_at.desc())
            .limit(5)
        )
        recent_runs = [
            {
                "run_id": r.run_id,
                "status": r.status,
                "artifacts_count": r.artifacts_count,
                "created_at": r.created_at.isoformat() if r.created_at else None,
                # `started_at` is what makes a *duration* statable. Without it the
                # dashboard could only subtract `created_at` from `completed_at`,
                # which is queue wait + execution — and it labelled that "Duration",
                # disagreeing with the run detail page about the same field (#674).
                "started_at": r.started_at.isoformat() if r.started_at else None,
                "completed_at": r.completed_at.isoformat() if r.completed_at else None,
            }
            for r in recent_rows
        ]

    return {
        "source_count": source_count,
        "total_runs": total_runs,
        "run_by_status": run_by_status,
        "total_artifacts": total_artifacts,
        "recent_runs": recent_runs,
    }
