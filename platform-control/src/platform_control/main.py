from __future__ import annotations

import uvicorn
from fastapi import FastAPI, Request
from fastapi.responses import JSONResponse

from platform_control.config import get_settings
from platform_control.errors import (
    InvalidStateTransitionError,
    NotFoundError,
    PlatformControlError,
    ProviderConfigurationError,
    SignatureVerificationError,
)
from platform_control.routers import firecrawl, health, runs, sources, versions


def create_app() -> FastAPI:
    settings = get_settings()
    app = FastAPI(title=settings.app_name, version="0.1.0")
    app.include_router(health.router)
    app.include_router(sources.router)
    app.include_router(versions.router)
    app.include_router(runs.router)
    app.include_router(firecrawl.router)

    @app.exception_handler(NotFoundError)
    async def not_found_handler(_: Request, exc: NotFoundError) -> JSONResponse:
        return JSONResponse(status_code=404, content={"detail": str(exc)})

    @app.exception_handler(InvalidStateTransitionError)
    async def conflict_handler(_: Request, exc: InvalidStateTransitionError) -> JSONResponse:
        return JSONResponse(status_code=409, content={"detail": str(exc)})

    @app.exception_handler(ProviderConfigurationError)
    async def provider_handler(_: Request, exc: ProviderConfigurationError) -> JSONResponse:
        return JSONResponse(status_code=400, content={"detail": str(exc)})

    @app.exception_handler(SignatureVerificationError)
    async def signature_handler(_: Request, exc: SignatureVerificationError) -> JSONResponse:
        return JSONResponse(status_code=401, content={"detail": str(exc)})

    @app.exception_handler(PlatformControlError)
    async def domain_handler(_: Request, exc: PlatformControlError) -> JSONResponse:
        return JSONResponse(status_code=400, content={"detail": str(exc)})

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
