"""Persistence abstractions for canonical output."""

import importlib
import json
import os
from collections.abc import Callable, Sequence
from dataclasses import dataclass, field

import pyarrow as pa

from document_intelligence.canonical.models import Document, ProcessingManifest, Section
from document_intelligence.errors import ProcessingError

# Delta append requires an Arrow schema compatible with the existing table. `_delta_ready_rows`
# normally drops keys that are null in every row; that narrows the schema and breaks append
# against legacy published surfaces (SchemaMismatchError: field count mismatch).
_PUBLISHED_DOCUMENTS_DELTA_KEYS = frozenset(
    {
        "document_id",
        "document_revision",
        "processing_manifest_id",
        "provenance",
        "primary_artifact_id",
        "jurisdiction_id",
        "authority_id",
        "title",
        "document_type",
        "processed_at",
        "processing_version",
        "lifecycle_status",
        "full_text",
        "body_text",
        "metadata",
    }
)
_PUBLISHED_SECTIONS_DELTA_KEYS = frozenset(
    {
        "section_id",
        "document_id",
        "document_revision",
        "processing_manifest_id",
        "provenance",
        "ordinal",
        "depth",
        "title",
        "content",
        "section_type",
        "metadata",
    }
)
_PROCESSING_MANIFESTS_DELTA_KEYS = frozenset(
    {
        "processing_manifest_id",
        "manifest_version",
        "document_id",
        "document_revision",
        "processing_version",
        "status",
        "provenance",
        "input_bundle_manifest_ref",
        "selected_profiles",
        "document_count",
        "section_count",
        "citation_count",
        "published_document_ref",
        "published_sections_ref",
        "canonical_ready_at",
    }
)


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
            always_present_keys=_PUBLISHED_DOCUMENTS_DELTA_KEYS,
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
            always_present_keys=_PUBLISHED_SECTIONS_DELTA_KEYS,
        )
        self._write_rows(
            self._config.processing_manifests_uri,
            [_manifest_dict_for_delta(manifest)],
            always_present_keys=_PROCESSING_MANIFESTS_DELTA_KEYS,
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
            ready = _delta_ready_rows(rows, always_present_keys=always_present_keys)
            mode = _delta_write_mode(uri)
            schema: pa.Schema | None = None
            if mode == "append":
                try:
                    deltalake_mod = importlib.import_module("deltalake")
                    schema = deltalake_mod.DeltaTable(uri).to_pyarrow_dataset().schema
                except Exception:
                    schema = None
            if schema is not None:
                table = pa.Table.from_pylist(ready, schema=schema)
            else:
                table = pa.Table.from_pylist(ready)
            self._writer(uri, table, mode=mode)
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


class SparkDeltaCanonicalSink(CanonicalSink):
    """Append canonical rows to Delta tables using the PySpark DataFrame writer.

    Designed for production Databricks jobs where a ``SparkSession`` is already
    active.  Prefers the PySpark Delta writer over the Python ``deltalake``
    library, which is driver-side only and not suitable for long-running cluster
    jobs that benefit from Spark's built-in schema evolution and transaction log
    management.

    Pass an explicit *spark* session for testing.  When *spark* is ``None`` the
    active ``SparkSession`` is resolved lazily via
    ``SparkSession.builder.getOrCreate()``.
    """

    def __init__(
        self,
        config: DeltaSinkConfig,
        *,
        spark: object | None = None,
    ) -> None:
        self._config = config
        self._spark = spark
        self.status_events: list[dict[str, object]] = []
        self.document_processed_events: list[dict[str, object]] = []

    def _get_spark(self) -> object:
        if self._spark is not None:
            return self._spark
        try:
            from pyspark.sql import SparkSession  # type: ignore[import-not-found]
        except ModuleNotFoundError as error:
            raise ProcessingError(
                "missing_pyspark_dependency",
                "pyspark is required for Spark-backed canonical persistence",
            ) from error
        return SparkSession.builder.getOrCreate()  # type: ignore[attr-defined]

    def persist(
        self,
        document: Document,
        sections: list[Section],
        manifest: ProcessingManifest,
    ) -> None:
        self._write_rows(
            self._config.published_documents_uri,
            [_document_dict_for_delta(document)],
            always_present_keys=_PUBLISHED_DOCUMENTS_DELTA_KEYS,
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
            always_present_keys=_PUBLISHED_SECTIONS_DELTA_KEYS,
        )
        self._write_rows(
            self._config.processing_manifests_uri,
            [_manifest_dict_for_delta(manifest)],
            always_present_keys=_PROCESSING_MANIFESTS_DELTA_KEYS,
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
            ready = _delta_ready_rows(rows, always_present_keys=always_present_keys)
            spark = self._get_spark()
            json_records = [json.dumps(row, default=str) for row in ready]
            rdd = spark.sparkContext.parallelize(json_records)  # type: ignore[attr-defined]
            df = spark.read.json(rdd)  # type: ignore[attr-defined]
            df.write.format("delta").mode("append").option("mergeSchema", "true").save(uri)  # type: ignore[attr-defined]
        except ProcessingError:
            raise
        except Exception as error:  # pragma: no cover - library-specific
            raise ProcessingError(
                "spark_delta_write_failed",
                f"failed to write canonical rows to Delta surface {uri} via PySpark",
            ) from error


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
    projected = [{key: value for key, value in row.items() if key in retained_keys} for row in normalized_rows]
    if always_present_keys:
        # Project to the exact published-surface column set so append matches the Delta schema and
        # optional model fields omitted from `to_dict()` still appear as null columns.
        return [{key: row.get(key, None) for key in always_present_keys} for row in projected]
    return projected


def _normalize_delta_value(value):
    if isinstance(value, dict):
        if not value:
            return None
        return {key: _normalize_delta_value(inner) for key, inner in value.items()}
    if isinstance(value, list):
        return [_normalize_delta_value(item) for item in value]
    return value
