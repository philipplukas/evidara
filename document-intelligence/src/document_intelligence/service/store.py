"""Load published documents from local fixtures or Delta-backed published surfaces."""

from __future__ import annotations

import importlib
import json
import logging
import os
import re
from pathlib import Path
from typing import Any, Protocol

from document_intelligence.config.runtime import RuntimeSettings
from document_intelligence.persist.sinks import delta_storage_options

_DOC_ID_RE = re.compile(r"^doc_[0-9a-hjkmnp-tv-z]{26}$")
_PM_ID_RE = re.compile(r"^pm_[0-9a-hjkmnp-tv-z]{26}$")
logger = logging.getLogger(__name__)


class PublishedDocumentStore(Protocol):
    def get_full(
        self,
        document_id: str,
        document_revision: int | None,
        processing_manifest_id: str | None = None,
    ) -> dict[str, Any] | None: ...


class EmptyPublishedDocumentStore:
    """Always misses (use when no content dir is configured)."""

    def get_full(
        self,
        document_id: str,
        document_revision: int | None,
        processing_manifest_id: str | None = None,
    ) -> dict[str, Any] | None:
        return None


class FilePublishedDocumentStore:
    """JSON files under a base directory."""

    def __init__(self, base_dir: Path) -> None:
        self._base = base_dir

    def get_full(
        self,
        document_id: str,
        document_revision: int | None,
        processing_manifest_id: str | None = None,
    ) -> dict[str, Any] | None:
        path = self._resolve_path(document_id, processing_manifest_id)
        if path is None or not path.is_file():
            return None
        return json.loads(path.read_text(encoding="utf-8"))

    def _resolve_path(self, document_id: str, processing_manifest_id: str | None) -> Path | None:
        if not _DOC_ID_RE.fullmatch(document_id):
            return None
        if processing_manifest_id is not None and not _PM_ID_RE.fullmatch(processing_manifest_id):
            return None

        if processing_manifest_id:
            return self._base / f"{document_id}__{processing_manifest_id}.json"

        default = self._base / f"{document_id}.json"
        if default.is_file():
            return default

        matches = sorted(self._base.glob(f"{document_id}__pm_*.json"))
        if matches:
            return matches[-1]
        return None


class DeltaPublishedDocumentStore:
    """Read published document rows from the Delta-backed published surface."""

    def __init__(
        self,
        published_documents_uri: str,
        published_sections_uri: str | None = None,
        storage_options: dict[str, str] | None = None,
    ) -> None:
        self._published_documents_uri = published_documents_uri
        self._published_sections_uri = published_sections_uri
        # ``None`` sentinel resolves MinIO / S3 credentials from ``DI_S3_*`` env vars so the read
        # API reaches the same object store the consumer wrote to; ``{}`` forces no options.
        self._storage_options = delta_storage_options() if storage_options is None else storage_options

    def _delta_table_kwargs(self) -> dict[str, Any]:
        return {"storage_options": self._storage_options} if self._storage_options else {}

    def get_full(
        self,
        document_id: str,
        document_revision: int | None,
        processing_manifest_id: str | None = None,
    ) -> dict[str, Any] | None:
        if not _DOC_ID_RE.fullmatch(document_id):
            return None
        if document_revision is not None and document_revision < 1:
            return None
        if processing_manifest_id is not None and not _PM_ID_RE.fullmatch(processing_manifest_id):
            return None

        deltalake = importlib.import_module("deltalake")
        dataset_mod = importlib.import_module("pyarrow.dataset")
        filters = [dataset_mod.field("document_id") == document_id]
        if document_revision is not None:
            filters.append(dataset_mod.field("document_revision") == document_revision)
        if processing_manifest_id is not None:
            filters.append(dataset_mod.field("processing_manifest_id") == processing_manifest_id)

        table = (
            deltalake.DeltaTable(self._published_documents_uri, **self._delta_table_kwargs())
            .to_pyarrow_dataset()
            .to_table(
                filter=_and_filters(filters),
            )
        )
        rows = table.to_pylist()
        if not rows:
            return None
        row = _pick_latest_row(rows)
        payload = _row_to_document_payload(row)
        sections = self._get_sections(
            document_id,
            int(row["document_revision"]) if row.get("document_revision") is not None else document_revision,
            str(row["processing_manifest_id"])
            if row.get("processing_manifest_id") is not None
            else processing_manifest_id,
        )
        if sections:
            payload["sections"] = sections
        return payload

    def _get_sections(
        self,
        document_id: str,
        document_revision: int | None,
        processing_manifest_id: str | None,
    ) -> list[dict[str, Any]]:
        if not self._published_sections_uri:
            return []

        deltalake = importlib.import_module("deltalake")
        dataset_mod = importlib.import_module("pyarrow.dataset")
        filters = [dataset_mod.field("document_id") == document_id]
        if document_revision is not None:
            filters.append(dataset_mod.field("document_revision") == document_revision)
        if processing_manifest_id is not None:
            filters.append(dataset_mod.field("processing_manifest_id") == processing_manifest_id)

        try:
            table = (
                deltalake.DeltaTable(self._published_sections_uri, **self._delta_table_kwargs())
                .to_pyarrow_dataset()
                .to_table(filter=_and_filters(filters))
            )
        except Exception as exc:  # pragma: no cover - depends on Delta backend failure mode
            logger.warning(
                "published_sections_unavailable",
                extra={"uri": self._published_sections_uri, "error": str(exc)},
            )
            return []

        rows = table.to_pylist()
        rows.sort(key=lambda row: (int(row.get("ordinal") or 0), str(row.get("section_id") or "")))
        return [_row_to_section_payload(row) for row in rows]


def store_from_env() -> PublishedDocumentStore | None:
    """Prefer Delta-backed published surfaces, then fall back to file fixtures."""
    runtime_settings = RuntimeSettings.from_environment()
    if runtime_settings.surface_uris is not None:
        return DeltaPublishedDocumentStore(
            runtime_settings.surface_uris.published_documents_uri,
            runtime_settings.surface_uris.published_sections_uri,
        )

    raw = os.environ.get("DOCUMENT_SERVICE_CONTENT_DIR", "").strip()
    if not raw:
        return None
    path = Path(raw).expanduser()
    if not path.is_dir():
        return None
    return FilePublishedDocumentStore(path)


def _pick_latest_row(rows: list[dict[str, Any]]) -> dict[str, Any]:
    return max(
        rows,
        key=lambda row: (
            int(row.get("document_revision") or 0),
            str(row.get("processed_at") or ""),
        ),
    )


def _row_to_document_payload(row: dict[str, Any]) -> dict[str, Any]:
    body: dict[str, Any] = {
        "document_id": row.get("document_id"),
        "document_revision": row.get("document_revision"),
        "processing_manifest_id": row.get("processing_manifest_id"),
        "jurisdiction_id": row.get("jurisdiction_id"),
        "authority_id": row.get("authority_id"),
        "title": row.get("title"),
        "document_type": row.get("document_type"),
        "effective_date": row.get("effective_date"),
        "processed_at": row.get("processed_at"),
        "processing_version": row.get("processing_version"),
        "lifecycle_status": row.get("lifecycle_status"),
        "full_text": row.get("full_text"),
        "body_text": row.get("body_text"),
    }
    metadata = row.get("metadata")
    if isinstance(metadata, dict):
        body["metadata"] = metadata
    extensions = row.get("extensions")
    if isinstance(extensions, dict):
        body["extensions"] = extensions
    provenance = row.get("provenance")
    if isinstance(provenance, dict):
        body["provenance"] = provenance
    return body


def _row_to_section_payload(row: dict[str, Any]) -> dict[str, Any]:
    body: dict[str, Any] = {
        "section_id": row.get("section_id"),
        "document_id": row.get("document_id"),
        "document_revision": row.get("document_revision"),
        "processing_manifest_id": row.get("processing_manifest_id"),
        "parent_section_id": row.get("parent_section_id"),
        "ordinal": row.get("ordinal"),
        "depth": row.get("depth"),
        "title": row.get("title"),
        "content": row.get("content"),
        "section_type": row.get("section_type"),
    }
    metadata = row.get("metadata")
    if isinstance(metadata, dict):
        body["metadata"] = metadata
    provenance = row.get("provenance")
    if isinstance(provenance, dict):
        body["provenance"] = provenance
    return body


def _and_filters(filters: list[Any]) -> Any:
    if not filters:
        raise ValueError("at least one filter is required")
    expr = filters[0]
    for item in filters[1:]:
        expr = expr & item
    return expr
