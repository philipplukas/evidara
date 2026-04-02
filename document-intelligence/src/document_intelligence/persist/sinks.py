"""Persistence abstractions for canonical output."""

import importlib
import os
from dataclasses import dataclass, field
from typing import Callable, Dict, List, Optional, Sequence

import pyarrow as pa

from document_intelligence.canonical.models import Document, ProcessingManifest, Section
from document_intelligence.errors import ProcessingError


class CanonicalSink:
    """Persistence interface for canonical writes and emitted events."""

    def persist(
        self,
        document: Document,
        sections: List[Section],
        manifest: ProcessingManifest,
    ) -> None:
        raise NotImplementedError

    def record_status_events(self, status_events: List[Dict[str, object]]) -> None:
        raise NotImplementedError

    def record_document_processed_event(
        self, document_processed_event: Dict[str, object]
    ) -> None:
        raise NotImplementedError


@dataclass(frozen=True)
class DeltaSinkConfig:
    published_documents_uri: str
    published_sections_uri: str
    processing_manifests_uri: str


@dataclass
class InMemoryCanonicalSink(CanonicalSink):
    published_documents: List[Document] = field(default_factory=list)
    published_sections: List[Section] = field(default_factory=list)
    processing_manifests: List[ProcessingManifest] = field(default_factory=list)
    status_events: List[Dict[str, object]] = field(default_factory=list)
    document_processed_events: List[Dict[str, object]] = field(default_factory=list)

    def persist(
        self,
        document: Document,
        sections: List[Section],
        manifest: ProcessingManifest,
    ) -> None:
        self.published_documents.append(document)
        self.published_sections.extend(sections)
        self.processing_manifests.append(manifest)

    def record_status_events(self, status_events: List[Dict[str, object]]) -> None:
        self.status_events.extend(status_events)

    def record_document_processed_event(
        self, document_processed_event: Dict[str, object]
    ) -> None:
        self.document_processed_events.append(document_processed_event)


class DeltaCanonicalSink(CanonicalSink):
    """Append canonical rows to Delta surfaces using the Python deltalake library."""

    def __init__(
        self,
        config: DeltaSinkConfig,
        *,
        writer: Optional[Callable[..., object]] = None,
    ) -> None:
        self._config = config
        self._writer = writer or _default_delta_writer()
        self.status_events: List[Dict[str, object]] = []
        self.document_processed_events: List[Dict[str, object]] = []

    def persist(
        self,
        document: Document,
        sections: List[Section],
        manifest: ProcessingManifest,
    ) -> None:
        self._write_rows(self._config.published_documents_uri, [document.to_dict()])
        self._write_rows(
            self._config.published_sections_uri,
            [section.to_dict() for section in sections],
        )
        self._write_rows(
            self._config.processing_manifests_uri,
            [manifest.to_dict()],
        )

    def record_status_events(self, status_events: List[Dict[str, object]]) -> None:
        self.status_events.extend(status_events)

    def record_document_processed_event(
        self, document_processed_event: Dict[str, object]
    ) -> None:
        self.document_processed_events.append(document_processed_event)

    def _write_rows(self, uri: str, rows: Sequence[Dict[str, object]]) -> None:
        if not rows:
            return
        try:
            table = pa.Table.from_pylist(_delta_ready_rows(rows))
            self._writer(uri, table, mode=_delta_write_mode(uri))
        except Exception as error:  # pragma: no cover - library-specific
            raise ProcessingError(
                "delta_write_failed",
                "failed to write canonical rows to Delta surface {uri}".format(uri=uri),
            ) from error


def _default_delta_writer() -> Callable[..., object]:
    try:
        deltalake_module = importlib.import_module("deltalake")
    except ModuleNotFoundError as error:  # pragma: no cover - depends on env
        raise ProcessingError(
            "missing_delta_dependency",
            "deltalake is required for Delta-backed canonical persistence",
        ) from error
    return deltalake_module.write_deltalake


def _delta_write_mode(uri: str) -> str:
    if uri.startswith("gs://"):
        return "append"
    local_path = uri[len("file://") :] if uri.startswith("file://") else uri
    delta_log_path = os.path.join(local_path, "_delta_log")
    return "append" if os.path.exists(delta_log_path) else "overwrite"


def _delta_ready_rows(rows: Sequence[Dict[str, object]]) -> List[Dict[str, object]]:
    normalized_rows = [
        {key: _normalize_delta_value(value) for key, value in row.items()}
        for row in rows
    ]
    retained_keys = {
        key
        for key in normalized_rows[0].keys()
        if any(row.get(key) is not None for row in normalized_rows)
    }
    return [
        {key: value for key, value in row.items() if key in retained_keys}
        for row in normalized_rows
    ]


def _normalize_delta_value(value):
    if isinstance(value, dict):
        if not value:
            return None
        return {key: _normalize_delta_value(inner) for key, inner in value.items()}
    if isinstance(value, list):
        return [_normalize_delta_value(item) for item in value]
    return value
