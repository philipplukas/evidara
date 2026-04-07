from __future__ import annotations

import json
import logging
import time
from uuid import uuid4

import uvicorn
from fastapi import Depends, FastAPI, Request
from fastapi.responses import JSONResponse

from platform_control.auth import require_control_plane_operator, require_control_plane_service
from platform_control.config import get_settings
from platform_control.errors import (
    ConflictError,
    InvalidStateTransitionError,
    NotFoundError,
    PlatformControlError,
    ProviderConfigurationError,
    SignatureVerificationError,
)
from platform_control.routers import (
    di_events,
    firecrawl,
    health,
    reference_data,
    reviews,
    runs,
    schedules,
    sources,
    versions,
    wizard,
)

_HTTP_LOGGER_NAME = "platform_control.http"


def _correlation_id_from_request(request: Request) -> str:
    return (
        request.headers.get("x-correlation-id")
        or request.headers.get("x-request-id")
        or str(uuid4())
    )


def _error_payload(request: Request, detail: str) -> dict[str, str]:
    correlation_id = getattr(request.state, "correlation_id", None)
    payload = {"detail": detail}
    if correlation_id:
        payload["correlation_id"] = correlation_id
    return payload


def create_app() -> FastAPI:
    settings = get_settings()
    app = FastAPI(title=settings.app_name, version="0.1.0")
    http_logger = logging.getLogger(_HTTP_LOGGER_NAME)

    @app.middleware("http")
    async def correlation_and_logging_middleware(request: Request, call_next):
        correlation_id = _correlation_id_from_request(request)
        request.state.correlation_id = correlation_id
        start = time.perf_counter()
        response = await call_next(request)
        duration_ms = round((time.perf_counter() - start) * 1000, 2)
        response.headers["X-Correlation-Id"] = correlation_id
        response.headers["X-Request-ID"] = correlation_id
        http_logger.info(
            json.dumps(
                {
                    "event": "http_request",
                    "service": settings.app_name,
                    "method": request.method,
                    "path": request.url.path,
                    "status_code": response.status_code,
                    "duration_ms": duration_ms,
                    "correlation_id": correlation_id,
                    "logger": _HTTP_LOGGER_NAME,
                }
            )
        )
        return response

    # Health endpoints — unauthenticated
    app.include_router(health.router)

    # Protected endpoints — see platform_control.auth for legacy vs scoped keys
    _operator_auth = [Depends(require_control_plane_operator)]
    _service_auth = [Depends(require_control_plane_service)]
    app.include_router(reference_data.router, dependencies=_operator_auth)
    app.include_router(sources.router, dependencies=_operator_auth)
    app.include_router(versions.router, dependencies=_operator_auth)
    app.include_router(runs.router, dependencies=_operator_auth)
    app.include_router(wizard.router, dependencies=_operator_auth)
    app.include_router(reviews.router, dependencies=_operator_auth)
    app.include_router(schedules.router, dependencies=_operator_auth)
    app.include_router(firecrawl.router, dependencies=_service_auth)
    app.include_router(di_events.router, dependencies=_service_auth)

    @app.exception_handler(NotFoundError)
    async def not_found_handler(request: Request, exc: NotFoundError) -> JSONResponse:
        return JSONResponse(status_code=404, content=_error_payload(request, str(exc)))

    @app.exception_handler(ConflictError)
    async def resource_conflict_handler(request: Request, exc: ConflictError) -> JSONResponse:
        return JSONResponse(status_code=409, content=_error_payload(request, str(exc)))

    @app.exception_handler(InvalidStateTransitionError)
    async def conflict_handler(request: Request, exc: InvalidStateTransitionError) -> JSONResponse:
        return JSONResponse(status_code=409, content=_error_payload(request, str(exc)))

    @app.exception_handler(ProviderConfigurationError)
    async def provider_handler(request: Request, exc: ProviderConfigurationError) -> JSONResponse:
        return JSONResponse(status_code=400, content=_error_payload(request, str(exc)))

    @app.exception_handler(SignatureVerificationError)
    async def signature_handler(request: Request, exc: SignatureVerificationError) -> JSONResponse:
        return JSONResponse(status_code=401, content=_error_payload(request, str(exc)))

    @app.exception_handler(PlatformControlError)
    async def domain_handler(request: Request, exc: PlatformControlError) -> JSONResponse:
        return JSONResponse(status_code=400, content=_error_payload(request, str(exc)))

    return app


app = create_app()


def run() -> None:
    settings = get_settings()
    uvicorn.run(
        "platform_control.main:app",
        host="0.0.0.0",
        port=8080,
        reload=settings.environment == "development",
    )
