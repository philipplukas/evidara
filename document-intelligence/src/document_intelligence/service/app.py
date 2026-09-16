"""FastAPI app for contracts/api/document-intelligence.openapi.yaml."""

from __future__ import annotations

import logging
import os
import re
from typing import Annotated, Any

from fastapi import Depends, FastAPI, Header, HTTPException, Query, Request
from fastapi.responses import JSONResponse, PlainTextResponse
from pydantic import BaseModel, Field

from document_intelligence.embeddings.query_encoding import (
    DEFAULT_MAX_FEATURES,
    MAX_FEATURES_CEILING,
    QueryEncoderUnavailable,
    encode_query,
)
from document_intelligence.http_observability import install_http_observability
from document_intelligence.service.lean import to_lean_dict, to_plain_text
from document_intelligence.service.store import (
    EmptyPublishedDocumentStore,
    PublishedDocumentStore,
    PublishedSectionsUnavailable,
    store_from_env,
)

_DOC_ID_RE = re.compile(r"^doc_[0-9a-hjkmnp-tv-z]{26}$")
_PM_ID_RE = re.compile(r"^pm_[0-9a-hjkmnp-tv-z]{26}$")

logger = logging.getLogger(__name__)


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


class QuerySparseRequest(BaseModel):
    """A query to encode into the `content_sparse` feature space (ADR-0054)."""

    query: str = Field(min_length=1, max_length=2000)
    max_features: int = Field(default=DEFAULT_MAX_FEATURES, ge=1, le=MAX_FEATURES_CEILING)


class QuerySparseResponse(BaseModel):
    #: `t<token-id>` -> weight, ready to send as `rank_feature` clauses. Token ids,
    #: never decoded strings: a multilingual vocabulary contains `.`, which OpenSearch
    #: reads as object nesting (see embeddings/sparse.py).
    features: dict[str, float]
    feature_count: int
    features_before_truncation: int
    #: Mass of the features ABOVE, not of the untruncated vector — ADR-0054 D4's
    #: coverage denominator has to describe the query that was actually issued.
    weight_mass: float
    truncated: bool
    model: str


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

    @app.exception_handler(PublishedSectionsUnavailable)
    async def _published_sections_unavailable(
        _request: Request,
        exc: PublishedSectionsUnavailable,
    ) -> JSONResponse:
        """Refuse, rather than serve a document that appears to have no sections (#972).

        The store raises this only when the sections read *failed*; a document with zero
        sections returns normally. Serving 200 here would state something false about the
        corpus — the shape #958 exists to remove — so the service answers 503 and the
        consumer can render "unavailable" instead of "none".
        """
        logger.warning("published_sections_unavailable_refusal", extra={"uri": exc.uri})
        return JSONResponse(
            status_code=503,
            content={
                "detail": (
                    "Published sections are temporarily unavailable for this document; "
                    "refusing to serve it as having none"
                )
            },
        )

    @app.get("/v1/documents/{document_id}", tags=["documents"])
    async def get_document_docling_full(
        document_id: str,
        document_revision: Annotated[int | None, Query(ge=1)] = None,
        processing_manifest_id: Annotated[str | None, Query(include_in_schema=False)] = None,
        _auth: None = Depends(verify_bearer),
        st: PublishedDocumentStore = Depends(get_store),
    ) -> dict[str, Any]:
        if not _DOC_ID_RE.fullmatch(document_id):
            raise _bad_id("Invalid document_id")
        if processing_manifest_id is not None and not _PM_ID_RE.fullmatch(processing_manifest_id):
            raise _bad_id("Invalid processing_manifest_id")
        body = st.get_full(document_id, document_revision, processing_manifest_id)
        if body is None:
            raise HTTPException(status_code=404, detail="Document revision not found")
        return body

    @app.get("/v1/documents/{document_id}/lean", tags=["documents"])
    async def get_document_docling_lean(
        document_id: str,
        document_revision: Annotated[int | None, Query(ge=1)] = None,
        processing_manifest_id: Annotated[str | None, Query(include_in_schema=False)] = None,
        _auth: None = Depends(verify_bearer),
        st: PublishedDocumentStore = Depends(get_store),
    ) -> dict[str, Any]:
        if not _DOC_ID_RE.fullmatch(document_id):
            raise _bad_id("Invalid document_id")
        if processing_manifest_id is not None and not _PM_ID_RE.fullmatch(processing_manifest_id):
            raise _bad_id("Invalid processing_manifest_id")
        body = st.get_full(document_id, document_revision, processing_manifest_id)
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
        document_revision: Annotated[int | None, Query(ge=1)] = None,
        processing_manifest_id: Annotated[str | None, Query(include_in_schema=False)] = None,
        _auth: None = Depends(verify_bearer),
        st: PublishedDocumentStore = Depends(get_store),
    ) -> PlainTextResponse:
        if not _DOC_ID_RE.fullmatch(document_id):
            raise _bad_id("Invalid document_id")
        if processing_manifest_id is not None and not _PM_ID_RE.fullmatch(processing_manifest_id):
            raise _bad_id("Invalid processing_manifest_id")
        body = st.get_full(document_id, document_revision, processing_manifest_id)
        if body is None:
            raise HTTPException(status_code=404, detail="Document revision not found")
        text = to_plain_text(body)
        return PlainTextResponse(content=text or "", media_type="text/plain; charset=utf-8")

    @app.post(
        "/v1/embeddings/query-sparse",
        tags=["embeddings"],
        response_model=QuerySparseResponse,
        responses={503: {"description": "This image does not carry the sparse encoder."}},
    )
    async def encode_query_sparse(
        payload: QuerySparseRequest,
        _auth: None = Depends(verify_bearer),
    ) -> QuerySparseResponse:
        """Encode a query so the search path can query `content_sparse`.

        503, not 500, when the encoder is absent: "this image has no model" and "this
        query is unanswerable" are different facts, and a search path that cannot tell
        them apart is the #958 defect at a service boundary. The named `reason` is in
        the detail so a caller can branch on it.
        """
        try:
            result = encode_query(payload.query, max_features=payload.max_features)
        except QueryEncoderUnavailable as exc:
            raise HTTPException(
                status_code=503,
                detail={"reason": exc.reason, "message": exc.detail},
            ) from exc
        except ValueError as exc:
            raise _bad_id(str(exc)) from exc
        return QuerySparseResponse(
            features=result.features,
            feature_count=len(result.features),
            features_before_truncation=result.features_before_truncation,
            weight_mass=result.weight_mass,
            truncated=result.truncated,
            model=result.model,
        )

    @app.get("/health", include_in_schema=False)
    async def health() -> dict[str, str]:
        return {"status": "ok"}

    return app
