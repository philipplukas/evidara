"""FastAPI app for internal artifact-bundle event ingestion."""

from __future__ import annotations

import os
from collections.abc import Callable
from typing import Any

from fastapi import Depends, FastAPI, Header, HTTPException

from document_intelligence.contracts.envelope import EnvelopeError
from document_intelligence.http_observability import install_http_observability
from document_intelligence.processing_runtime import process_artifact_bundle_event


def verify_ingest_bearer(
    authorization: str | None = Header(default=None),
) -> None:
    expected = os.environ.get("DOCUMENT_INTELLIGENCE_INGEST_BEARER_TOKEN", "").strip()
    if not expected:
        expected = os.environ.get("DOCUMENT_SERVICE_BEARER_TOKEN", "").strip()
    if not expected:
        return
    if not authorization or not authorization.startswith("Bearer "):
        raise HTTPException(status_code=401, detail="Missing or invalid Authorization header")
    token = authorization.removeprefix("Bearer ").strip()
    if token != expected:
        raise HTTPException(status_code=401, detail="Invalid bearer token")


def create_app(
    event_processor: Callable[[dict[str, Any]], dict[str, Any]] | None = None,
) -> FastAPI:
    def _default_event_processor(body: dict[str, Any]) -> dict[str, Any]:
        return process_artifact_bundle_event(body, require_surface_uris=True)

    processor = event_processor or _default_event_processor

    app = FastAPI(
        title="Document Intelligence — Runtime Ingress",
        version="0.1.0",
        openapi_url="/openapi.json",
    )
    install_http_observability(app, "document-intelligence-consumer")

    @app.post("/internal/events/artifact-bundles:process", tags=["ingestion"])
    async def process_artifact_bundle(
        body: dict[str, Any],
        _auth: None = Depends(verify_ingest_bearer),
    ) -> dict[str, Any]:
        try:
            return processor(body)
        except EnvelopeError as error:
            raise HTTPException(status_code=400, detail=str(error)) from error

    @app.get("/health", include_in_schema=False)
    async def health() -> dict[str, str]:
        return {"status": "ok"}

    return app
