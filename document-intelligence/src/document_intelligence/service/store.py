"""Load published Docling JSON from a local content directory (dev / thin deployments)."""

from __future__ import annotations

import json
import os
import re
from pathlib import Path
from typing import Any, Protocol

_DOC_ID_RE = re.compile(r"^doc_[0-9a-hjkmnp-tv-z]{26}$")
_PM_ID_RE = re.compile(r"^pm_[0-9a-hjkmnp-tv-z]{26}$")


class PublishedDocumentStore(Protocol):
    def get_full(
        self,
        document_id: str,
        processing_manifest_id: str | None,
    ) -> dict[str, Any] | None: ...


class EmptyPublishedDocumentStore:
    """Always misses (use when no content dir is configured)."""

    def get_full(
        self,
        document_id: str,
        processing_manifest_id: str | None,
    ) -> dict[str, Any] | None:
        return None


class FilePublishedDocumentStore:
    """JSON files under a base directory."""

    def __init__(self, base_dir: Path) -> None:
        self._base = base_dir

    def get_full(
        self,
        document_id: str,
        processing_manifest_id: str | None,
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


def store_from_env() -> FilePublishedDocumentStore | None:
    """Return file store when DOCUMENT_SERVICE_CONTENT_DIR is set to an existing directory."""
    raw = os.environ.get("DOCUMENT_SERVICE_CONTENT_DIR", "").strip()
    if not raw:
        return None
    path = Path(raw).expanduser()
    if not path.is_dir():
        return None
    return FilePublishedDocumentStore(path)
