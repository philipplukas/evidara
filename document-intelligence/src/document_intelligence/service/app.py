"""FastAPI app for contracts/api/document-intelligence.openapi.yaml."""

from __future__ import annotations

import os
import re
from typing import Annotated, Any

from fastapi import Depends, FastAPI, Header, HTTPException, Query
from fastapi.responses import PlainTextResponse

from document_intelligence.http_observability import install_http_observability
from document_intelligence.service.lean import to_lean_dict, to_plain_text
from document_intelligence.service.store import (
    EmptyPublishedDocumentStore,
    PublishedDocumentStore,
    store_from_env,
)

_DOC_ID_RE = re.compile(r"^doc_[0-9a-hjkmnp-tv-z]{26}$")
_PM_ID_RE = re.compile(r"^pm_[0-9a-hjkmnp-tv-z]{26}$")


def _bad_id(message: str) -> HTTPException:
    return HTTPException(status_code=400, detail=message)


def verify_bearer(
    authorization: Annotated[str | None, Header()] = None,
) -> None:
    expected = os.environ.get("DOCUMENT_SERVICE_BEARER_TOKEN", "").strip()
    if not expected:
        return
    if not authorization or not authorization.startswith("Bearer "):
        raise HTTPException(status_code=401, detail="Missing or invalid Authorization header")
    token = authorization.removeprefix("Bearer ").strip()
    if token != expected:
        raise HTTPException(status_code=401, detail="Invalid bearer token")


def create_app(store: PublishedDocumentStore | None = None) -> FastAPI:
    """Create app; uses ``DOCUMENT_SERVICE_CONTENT_DIR`` when ``store`` is omitted."""
    effective: PublishedDocumentStore = (
        store if store is not None else (store_from_env() or EmptyPublishedDocumentStore())
    )

    app = FastAPI(
        title="Document Intelligence — Document Service",
        version="0.1.0",
        openapi_url="/openapi.json",
    )
    install_http_observability(app, "document-intelligence-service")

    def get_store() -> PublishedDocumentStore:
        return effective

    @app.get("/v1/documents/{document_id}", tags=["documents"])
    async def get_document_docling_full(
        document_id: str,
        processing_manifest_id: Annotated[str | None, Query()] = None,
        _auth: None = Depends(verify_bearer),
        st: PublishedDocumentStore = Depends(get_store),
    ) -> dict[str, Any]:
        if not _DOC_ID_RE.fullmatch(document_id):
            raise _bad_id("Invalid document_id")
        if processing_manifest_id is not None and not _PM_ID_RE.fullmatch(processing_manifest_id):
            raise _bad_id("Invalid processing_manifest_id")
        body = st.get_full(document_id, processing_manifest_id)
        if body is None:
            raise HTTPException(status_code=404, detail="Document revision not found")
        return body

    @app.get("/v1/documents/{document_id}/lean", tags=["documents"])
    async def get_document_docling_lean(
        document_id: str,
        processing_manifest_id: Annotated[str | None, Query()] = None,
        _auth: None = Depends(verify_bearer),
        st: PublishedDocumentStore = Depends(get_store),
    ) -> dict[str, Any]:
        if not _DOC_ID_RE.fullmatch(document_id):
            raise _bad_id("Invalid document_id")
        if processing_manifest_id is not None and not _PM_ID_RE.fullmatch(processing_manifest_id):
            raise _bad_id("Invalid processing_manifest_id")
        body = st.get_full(document_id, processing_manifest_id)
        if body is None:
            raise HTTPException(status_code=404, detail="Document revision not found")
        return to_lean_dict(body)

    @app.get(
        "/v1/documents/{document_id}/text",
        tags=["documents"],
        response_class=PlainTextResponse,
    )
    async def get_document_plain_text(
        document_id: str,
        processing_manifest_id: Annotated[str | None, Query()] = None,
        _auth: None = Depends(verify_bearer),
        st: PublishedDocumentStore = Depends(get_store),
    ) -> PlainTextResponse:
        if not _DOC_ID_RE.fullmatch(document_id):
            raise _bad_id("Invalid document_id")
        if processing_manifest_id is not None and not _PM_ID_RE.fullmatch(processing_manifest_id):
            raise _bad_id("Invalid processing_manifest_id")
        body = st.get_full(document_id, processing_manifest_id)
        if body is None:
            raise HTTPException(status_code=404, detail="Document revision not found")
        text = to_plain_text(body)
        return PlainTextResponse(content=text or "", media_type="text/plain; charset=utf-8")

    @app.get("/health", include_in_schema=False)
    async def health() -> dict[str, str]:
        return {"status": "ok"}

    return app
