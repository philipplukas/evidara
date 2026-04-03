from fastapi import APIRouter
from fastapi.responses import JSONResponse
from sqlalchemy import text

from platform_control.config import get_settings
from platform_control.database import get_session_maker
from platform_control.schemas.health import DependencyCheck, HealthResponse, ReadinessResponse

router = APIRouter(tags=["health"])


@router.get("/health", response_model=HealthResponse)
async def get_health() -> HealthResponse:
    settings = get_settings()
    return HealthResponse(status="ok", service=settings.app_name)


@router.get("/ready", response_model=ReadinessResponse)
async def get_readiness() -> JSONResponse:
    settings = get_settings()
    session_maker = get_session_maker()
    checks: dict[str, DependencyCheck] = {}

    try:
        async with session_maker() as session:
            await session.execute(text("SELECT 1"))
        checks["database"] = DependencyCheck(status="ok")
    except Exception as error:  # pragma: no cover - defensive runtime safety
        checks["database"] = DependencyCheck(
            status="error",
            detail=f"database_unreachable: {error}",
        )

    status = "ok" if all(check.status == "ok" for check in checks.values()) else "degraded"
    payload = ReadinessResponse(status=status, service=settings.app_name, checks=checks)
    http_status = 200 if status == "ok" else 503
    return JSONResponse(status_code=http_status, content=payload.model_dump())
