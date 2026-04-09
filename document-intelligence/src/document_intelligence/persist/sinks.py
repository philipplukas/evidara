"""Persistence abstractions for canonical output."""

import importlib
import os
from collections.abc import Callable, Sequence
from dataclasses import dataclass, field

import pyarrow as pa

from document_intelligence.canonical.models import Document, ProcessingManifest, Section
from document_intelligence.errors import ProcessingError


def _document_dict_for_delta(document: Document) -> dict[str, object]:
    """Match legacy `published_documents` Delta schemas (no extensions / effective_date)."""
    row = document.to_dict()
    row.pop("extensions", None)
    row.pop("effective_date", None)
    return row


def _manifest_dict_for_delta(manifest: ProcessingManifest) -> dict[str, object]:
    """Match legacy `processing_manifests` nested structs (e.g. storage_ref without created_at)."""
    row = manifest.to_dict()
    ibmr = row.get("input_bundle_manifest_ref")
    if isinstance(ibmr, dict):
        storage_ref = ibmr.get("storage_ref")
        if isinstance(storage_ref, dict):
            storage_ref.pop("created_at", None)
    return row


class CanonicalSink:
    """Persistence interface for canonical writes and emitted events."""

    def persist(
        self,
        document: Document,
        sections: list[Section],
        manifest: ProcessingManifest,
    ) -> None:
        raise NotImplementedError

    def record_status_events(self, status_events: list[dict[str, object]]) -> None:
        raise NotImplementedError

    def record_document_processed_event(self, document_processed_event: dict[str, object]) -> None:
        raise NotImplementedError


@dataclass(frozen=True)
class DeltaSinkConfig:
    published_documents_uri: str
    published_sections_uri: str
    processing_manifests_uri: str


@dataclass
class InMemoryCanonicalSink(CanonicalSink):
    published_documents: list[Document] = field(default_factory=list)
    published_sections: list[Section] = field(default_factory=list)
    processing_manifests: list[ProcessingManifest] = field(default_factory=list)
    status_events: list[dict[str, object]] = field(default_factory=list)
    document_processed_events: list[dict[str, object]] = field(default_factory=list)

    def persist(
        self,
        document: Document,
        sections: list[Section],
        manifest: ProcessingManifest,
    ) -> None:
        self.published_documents.append(document)
        self.published_sections.extend(sections)
        self.processing_manifests.append(manifest)

    def record_status_events(self, status_events: list[dict[str, object]]) -> None:
        self.status_events.extend(status_events)

    def record_document_processed_event(self, document_processed_event: dict[str, object]) -> None:
        self.document_processed_events.append(document_processed_event)


class DeltaCanonicalSink(CanonicalSink):
    """Append canonical rows to Delta surfaces using the Python deltalake library."""

    def __init__(
        self,
        config: DeltaSinkConfig,
        *,
        writer: Callable[..., object] | None = None,
    ) -> None:
        self._config = config
        self._writer = writer or _default_delta_writer()
        self.status_events: list[dict[str, object]] = []
        self.document_processed_events: list[dict[str, object]] = []

    def persist(
        self,
        document: Document,
        sections: list[Section],
        manifest: ProcessingManifest,
    ) -> None:
        self._write_rows(
            self._config.published_documents_uri,
            [_document_dict_for_delta(document)],
        )
        # Published Delta tables predate `parent_section_id`; omit until schemas are migrated.
        section_rows = []
        for section in sections:
            row = section.to_dict()
            row.pop("parent_section_id", None)
            section_rows.append(row)
        self._write_rows(
            self._config.published_sections_uri,
            section_rows,
            always_present_keys=frozenset({"metadata"}),
        )
        self._write_rows(
            self._config.processing_manifests_uri,
            [_manifest_dict_for_delta(manifest)],
        )

    def record_status_events(self, status_events: list[dict[str, object]]) -> None:
        self.status_events.extend(status_events)

    def record_document_processed_event(self, document_processed_event: dict[str, object]) -> None:
        self.document_processed_events.append(document_processed_event)

    def _write_rows(
        self,
        uri: str,
        rows: Sequence[dict[str, object]],
        *,
        always_present_keys: frozenset[str] | None = None,
    ) -> None:
        if not rows:
            return
        try:
            table = pa.Table.from_pylist(_delta_ready_rows(rows, always_present_keys=always_present_keys))
            self._writer(uri, table, mode=_delta_write_mode(uri))
        except Exception as error:  # pragma: no cover - library-specific
            raise ProcessingError(
                "delta_write_failed",
                f"failed to write canonical rows to Delta surface {uri}",
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


def _delta_ready_rows(
    rows: Sequence[dict[str, object]],
    *,
    always_present_keys: frozenset[str] | None = None,
) -> list[dict[str, object]]:
    normalized_rows = [{key: _normalize_delta_value(value) for key, value in row.items()} for row in rows]
    retained_keys = {
        key for key in normalized_rows[0].keys() if any(row.get(key) is not None for row in normalized_rows)
    }
    if always_present_keys:
        retained_keys |= always_present_keys
    return [{key: value for key, value in row.items() if key in retained_keys} for row in normalized_rows]


def _normalize_delta_value(value):
    if isinstance(value, dict):
        if not value:
            return None
        return {key: _normalize_delta_value(inner) for key, inner in value.items()}
    if isinstance(value, list):
        return [_normalize_delta_value(item) for item in value]
    return value
