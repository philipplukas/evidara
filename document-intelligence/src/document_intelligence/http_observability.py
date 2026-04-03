from __future__ import annotations

import json
import logging
import time
from uuid import uuid4

from fastapi import FastAPI, Request


def _correlation_id_from_request(request: Request) -> str:
    return (
        request.headers.get("x-correlation-id")
        or request.headers.get("x-request-id")
        or str(uuid4())
    )


def install_http_observability(app: FastAPI, service_name: str) -> None:
    logger = logging.getLogger(f"{service_name}.http")

    @app.middleware("http")
    async def _correlation_and_request_log(request: Request, call_next):
        correlation_id = _correlation_id_from_request(request)
        request.state.correlation_id = correlation_id
        started = time.perf_counter()
        response = await call_next(request)
        duration_ms = round((time.perf_counter() - started) * 1000, 2)
        response.headers["X-Correlation-Id"] = correlation_id
        response.headers["X-Request-ID"] = correlation_id
        logger.info(
            json.dumps(
                {
                    "event": "http_request",
                    "service": service_name,
                    "method": request.method,
                    "path": request.url.path,
                    "status_code": response.status_code,
                    "duration_ms": duration_ms,
                    "correlation_id": correlation_id,
                }
            )
        )
        return response
