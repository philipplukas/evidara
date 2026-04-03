"""FastAPI app for internal artifact-bundle event ingestion."""

from __future__ import annotations

import os
from collections.abc import Callable
from typing import Any, Optional

from fastapi import Depends, FastAPI, Header, HTTPException

from document_intelligence.contracts.envelope import EnvelopeError
from document_intelligence.processing_runtime import process_artifact_bundle_event


def verify_ingest_bearer(
    authorization: Optional[str] = Header(default=None),
) -> None:
    expected = os.environ.get("DOCUMENT_INTELLIGENCE_INGEST_BEARER_TOKEN", "").strip()
    if not expected:
        expected = os.environ.get("DOCUMENT_SERVICE_BEARER_TOKEN", "").strip()
    if not expected:
        return
    if not authorization or not authorization.startswith("Bearer "):
        raise HTTPException(
            status_code=401, detail="Missing or invalid Authorization header"
        )
    token = authorization.removeprefix("Bearer ").strip()
    if token != expected:
        raise HTTPException(status_code=401, detail="Invalid bearer token")


def create_app(
    event_processor: Callable[[dict[str, Any]], dict[str, Any]] | None = None,
) -> FastAPI:
    processor = event_processor or process_artifact_bundle_event

    app = FastAPI(
        title="Document Intelligence — Runtime Ingress",
        version="0.1.0",
        openapi_url="/openapi.json",
    )

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
