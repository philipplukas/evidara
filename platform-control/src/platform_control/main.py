from __future__ import annotations

import json
import logging
import time
from uuid import uuid4

import uvicorn
from fastapi import Depends, FastAPI, Request
from fastapi.responses import JSONResponse

from acquisition_core.providers import ProviderNotLiveReadyError
from platform_control.auth import (
    check_auth_configuration,
    require_control_plane_operator,
    require_control_plane_service,
)
from platform_control.config import get_settings
from platform_control.errors import (
    ConflictError,
    DispatchPublishError,
    InvalidStateTransitionError,
    NotFoundError,
    PlatformControlError,
    ProviderConfigurationError,
    SignatureVerificationError,
    WebhookRetryableError,
)
from platform_control.openapi import (
    API_CONTACT,
    API_DESCRIPTION,
    API_TITLE,
    API_VERSION,
    OPENAPI_TAGS,
    generate_operation_id,
)
from platform_control.routers import (
    commentary_insights,
    compliance_policies,
    corrections,
    coverage,
    di_events,
    firecrawl,
    health,
    reference_data,
    reviews,
    runs,
    schedules,
    slack_interactions,
    sources,
    versions,
    wizard,
)
from platform_control.routers.corpora import router as corpora_router
from platform_control.schemas.errors import ErrorResponse

_HTTP_LOGGER_NAME = "platform_control.http"


def _correlation_id_from_request(request: Request) -> str:
    return (
        request.headers.get("x-correlation-id")
        or request.headers.get("x-request-id")
        or str(uuid4())
    )


def _error_payload(request: Request, detail: str) -> dict[str, str]:
    # Built through ErrorResponse so the body the handlers send and the body the
    # routes declare (`error_responses(...)`) cannot drift apart — see #627.
    correlation_id = getattr(request.state, "correlation_id", None)
    payload = ErrorResponse(detail=detail, correlation_id=correlation_id or None)
    return payload.model_dump(exclude_none=True)


def create_app() -> FastAPI:
    settings = get_settings()
    # Document metadata lives in platform_control.openapi because this app *is*
    # the source of truth for contracts/api/platform-control.openapi.yaml — the
    # contract is generated from `app.openapi()` and gated for drift (#618).
    # The title was previously `settings.app_name` ("platform-control") and the
    # version a frozen "0.1.0"; both are now the contract's own identity, which
    # scripts/check_contract_manifest.py pins to contracts/manifest.yaml.
    app = FastAPI(
        title=API_TITLE,
        version=API_VERSION,
        description=API_DESCRIPTION,
        contact=API_CONTACT,
        openapi_tags=OPENAPI_TAGS,
        generate_unique_id_function=generate_operation_id,
    )
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

    # Fail-closed auth: surface a missing key at boot, not only as a 503 on the first
    # request. `create_app` deliberately does not raise — the ADR-0034 contract
    # generator imports it at build time with no environment — but a deployment that
    # reaches this log line and ignores it is serving nothing but 503s.
    _auth_problem = check_auth_configuration(settings)
    if _auth_problem is not None:
        logging.getLogger(__name__).critical(_auth_problem)

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
    app.include_router(corpora_router, dependencies=_operator_auth)
    app.include_router(compliance_policies.router, dependencies=_operator_auth)
    app.include_router(corrections.router, dependencies=_operator_auth)
    app.include_router(coverage.router, dependencies=_operator_auth)
    app.include_router(commentary_insights.router, dependencies=_operator_auth)
    app.include_router(firecrawl.router, dependencies=_service_auth)
    app.include_router(di_events.router, dependencies=_service_auth)

    # Slack interactions — unauthenticated (Slack signature verification handled in-route)
    app.include_router(slack_interactions.router)

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

    @app.exception_handler(ProviderNotLiveReadyError)
    async def provider_not_live_ready_handler(
        request: Request, exc: ProviderNotLiveReadyError
    ) -> JSONResponse:
        # Provider-side key of the ADR-0030 two-key lock. Same 400 family as
        # ProviderConfigurationError: the provider cannot serve this request.
        # BlueprintTemplateNotEnabledError (config-side key) is a
        # PlatformControlError and lands on the domain handler below, also 400.
        return JSONResponse(status_code=400, content=_error_payload(request, str(exc)))

    @app.exception_handler(DispatchPublishError)
    async def dispatch_publish_handler(request: Request, exc: DispatchPublishError) -> JSONResponse:
        # 502, not 500: the request was valid and acquisition succeeded — the
        # downstream broker refused the handoff. A bare 500 is what #707 returned,
        # and it told the caller nothing while the run read `completed`. The run has
        # already been rewritten to FAILED with this same reason, so the API answer
        # and the persisted record now agree.
        return JSONResponse(status_code=502, content=_error_payload(request, str(exc)))

    @app.exception_handler(SignatureVerificationError)
    async def signature_handler(request: Request, exc: SignatureVerificationError) -> JSONResponse:
        return JSONResponse(status_code=401, content=_error_payload(request, str(exc)))

    @app.exception_handler(WebhookRetryableError)
    async def webhook_retryable_handler(
        request: Request, exc: WebhookRetryableError
    ) -> JSONResponse:
        # 503, not 202: the delivery was stored unprocessed and the sender MUST retry it.
        # A 2xx would tell the provider the event was accepted while nothing was applied,
        # and the identical retry would then be deduped away — the #558 drop.
        return JSONResponse(
            status_code=503,
            content=_error_payload(request, str(exc)),
            headers={"Retry-After": "5"},
        )

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
