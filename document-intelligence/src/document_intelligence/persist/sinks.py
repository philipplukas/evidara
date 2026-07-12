"""Persistence abstractions for canonical output."""

import importlib
import json
import os
from collections.abc import Callable, Mapping, Sequence
from dataclasses import dataclass, field

import pyarrow as pa

from document_intelligence.canonical.models import CommentaryInsight, Document, ProcessingManifest, Section
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
        "extensions",
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
_PUBLISHED_COMMENTARY_INSIGHTS_DELTA_KEYS = frozenset(
    {
        "insight_id",
        "document_id",
        "document_revision",
        "processing_manifest_id",
        "section_id",
        "citation_id",
        "insight_type",
        "claim",
        "display_text",
        "support",
        "referenced_authorities",
        "language",
        "jurisdiction_id",
        "confidence",
        "review_state",
        "generator",
        "scores",
        "metadata",
    }
)
_STRING_MAP = pa.map_(pa.string(), pa.string())
_COMMENTARY_INSIGHTS_ARROW_SCHEMA = pa.schema(
    [
        pa.field("insight_id", pa.string()),
        pa.field("document_id", pa.string()),
        pa.field("document_revision", pa.int64()),
        pa.field("processing_manifest_id", pa.string()),
        pa.field("section_id", pa.string()),
        pa.field("citation_id", pa.string()),
        pa.field("insight_type", pa.string()),
        pa.field("claim", pa.string()),
        pa.field("display_text", pa.string()),
        pa.field(
            "support",
            pa.list_(
                pa.struct(
                    [
                        pa.field("document_id", pa.string()),
                        pa.field("section_id", pa.string()),
                        pa.field("citation_id", pa.string()),
                        pa.field("ref_type", pa.string()),
                        pa.field("passage", pa.string()),
                        pa.field("confidence", pa.float64()),
                        pa.field("metadata", _STRING_MAP),
                    ]
                )
            ),
        ),
        pa.field(
            "referenced_authorities",
            pa.list_(
                pa.struct(
                    [
                        pa.field("text", pa.string()),
                        pa.field("citation_type", pa.string()),
                        pa.field("normalized_reference", pa.string()),
                        pa.field("metadata", _STRING_MAP),
                    ]
                )
            ),
        ),
        pa.field("language", pa.string()),
        pa.field("jurisdiction_id", pa.string()),
        pa.field("confidence", pa.float64()),
        pa.field("review_state", pa.string()),
        pa.field(
            "generator",
            pa.struct(
                [
                    pa.field("name", pa.string()),
                    pa.field("version", pa.string()),
                    pa.field("model", pa.string()),
                    pa.field("prompt_version", pa.string()),
                ]
            ),
        ),
        pa.field(
            "scores",
            pa.struct(
                [
                    pa.field("passage_present", pa.float64()),
                    pa.field("citation_parseable", pa.float64()),
                    pa.field("section_anchor_resolved", pa.float64()),
                ]
            ),
        ),
        pa.field("metadata", _STRING_MAP),
    ]
)


def _document_dict_for_delta(document: Document) -> dict[str, object]:
    """Match legacy `published_documents` Delta schemas while preserving extension payloads."""
    row = document.to_dict()
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


def _commentary_insight_dict_for_delta(insight: CommentaryInsight) -> dict[str, object]:
    row = insight.to_dict()
    row["metadata"] = _stringify_mapping_values(row.get("metadata"))

    support = []
    for item in row.get("support") or []:
        if isinstance(item, dict):
            support_item = dict(item)
            support_item["metadata"] = _stringify_mapping_values(support_item.get("metadata"))
            support.append(support_item)
    row["support"] = support

    referenced_authorities = []
    for item in row.get("referenced_authorities") or []:
        if isinstance(item, dict):
            authority = dict(item)
            authority.setdefault("normalized_reference", None)
            authority["metadata"] = _stringify_mapping_values(authority.get("metadata"))
            referenced_authorities.append(authority)
    row["referenced_authorities"] = referenced_authorities
    return row


def _stringify_mapping_values(value: object) -> dict[str, str]:
    if not isinstance(value, dict):
        return {}
    return {str(key): str(inner) for key, inner in value.items() if inner is not None}


def delta_storage_options(environ: Mapping[str, str] | None = None) -> dict[str, str] | None:
    """Build ``deltalake`` ``storage_options`` for a MinIO / S3 endpoint from ``DI_S3_*`` env vars.

    Returns ``None`` when ``DI_S3_ENDPOINT_URL`` is unset — ``file://``, plain local paths and
    ``gs://`` surfaces need no options, so the default (env-driven) object-store credentials apply.
    Mirrors the S3 client wiring in ``ingest.loaders`` so the self-hosted (Hetzner / MinIO) consumer
    and read API resolve the same endpoint and credentials.
    """
    env = environ if environ is not None else os.environ
    endpoint = (env.get("DI_S3_ENDPOINT_URL") or "").strip()
    if not endpoint:
        return None
    options: dict[str, str] = {
        "AWS_ENDPOINT_URL": endpoint,
        # MinIO in-cluster is reached over plain HTTP; object_store rejects it unless allowed.
        "AWS_ALLOW_HTTP": "true" if endpoint.startswith("http://") else "false",
        # Single-writer consumer without a DynamoDB lock table: permit the rename-based commit.
        "AWS_S3_ALLOW_UNSAFE_RENAME": "true",
    }
    region = (env.get("DI_S3_REGION") or "").strip()
    if region:
        options["AWS_REGION"] = region
    access_key_id = (env.get("DI_S3_ACCESS_KEY_ID") or "").strip()
    secret_access_key = (env.get("DI_S3_SECRET_ACCESS_KEY") or "").strip()
    if access_key_id and secret_access_key:
        options["AWS_ACCESS_KEY_ID"] = access_key_id
        options["AWS_SECRET_ACCESS_KEY"] = secret_access_key
    return options


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

    def persist_commentary_insights(self, commentary_insights: list[CommentaryInsight]) -> None:
        raise NotImplementedError


@dataclass(frozen=True)
class DeltaSinkConfig:
    published_documents_uri: str
    published_sections_uri: str
    processing_manifests_uri: str
    published_commentary_insights_uri: str | None = None


@dataclass
class InMemoryCanonicalSink(CanonicalSink):
    published_documents: list[Document] = field(default_factory=list)
    published_sections: list[Section] = field(default_factory=list)
    processing_manifests: list[ProcessingManifest] = field(default_factory=list)
    published_commentary_insights: list[CommentaryInsight] = field(default_factory=list)
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

    def persist_commentary_insights(self, commentary_insights: list[CommentaryInsight]) -> None:
        self.published_commentary_insights.extend(commentary_insights)


class DeltaCanonicalSink(CanonicalSink):
    """Append canonical rows to Delta surfaces using the Python deltalake library."""

    def __init__(
        self,
        config: DeltaSinkConfig,
        *,
        writer: Callable[..., object] | None = None,
        storage_options: dict[str, str] | None = None,
    ) -> None:
        self._config = config
        self._writer = writer or _default_delta_writer()
        # ``None`` sentinel means "resolve from the environment"; pass ``{}`` to force no options.
        self._storage_options = delta_storage_options() if storage_options is None else storage_options
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

    def persist_commentary_insights(self, commentary_insights: list[CommentaryInsight]) -> None:
        if not commentary_insights:
            return
        if not self._config.published_commentary_insights_uri:
            raise ProcessingError(
                "missing_commentary_insights_surface",
                "published commentary insights URI is required when commentary insights are emitted",
            )
        self._write_rows(
            self._config.published_commentary_insights_uri,
            [_commentary_insight_dict_for_delta(insight) for insight in commentary_insights],
            always_present_keys=_PUBLISHED_COMMENTARY_INSIGHTS_DELTA_KEYS,
            schema_override=_COMMENTARY_INSIGHTS_ARROW_SCHEMA,
        )

    def _write_rows(
        self,
        uri: str,
        rows: Sequence[dict[str, object]],
        *,
        always_present_keys: frozenset[str] | None = None,
        schema_override: pa.Schema | None = None,
    ) -> None:
        if not rows:
            return
        try:
            ready = _delta_ready_rows(
                rows,
                always_present_keys=_projection_keys_for_rows(rows, always_present_keys),
            )
            mode = _delta_write_mode(uri)
            schema: pa.Schema | None = schema_override
            if mode == "append":
                try:
                    deltalake_mod = importlib.import_module("deltalake")
                    table_kwargs = {"storage_options": self._storage_options} if self._storage_options else {}
                    schema = deltalake_mod.DeltaTable(uri, **table_kwargs).to_pyarrow_dataset().schema
                except Exception:
                    schema = schema_override
            if schema is not None:
                incoming_keys = {key for row in ready for key in row.keys()}
                if not incoming_keys.issubset(set(schema.names)):
                    schema = None
            if schema is not None:
                table = pa.Table.from_pylist(ready, schema=schema)
            else:
                table = pa.Table.from_pylist(ready)
            writer_kwargs: dict[str, object] = {"mode": mode}
            if mode == "append":
                writer_kwargs["schema_mode"] = "merge"
            if self._storage_options:
                writer_kwargs["storage_options"] = self._storage_options
            self._writer(uri, table, **writer_kwargs)
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

    def persist_commentary_insights(self, commentary_insights: list[CommentaryInsight]) -> None:
        if not commentary_insights:
            return
        if not self._config.published_commentary_insights_uri:
            raise ProcessingError(
                "missing_commentary_insights_surface",
                "published commentary insights URI is required when commentary insights are emitted",
            )
        self._write_rows(
            self._config.published_commentary_insights_uri,
            [_commentary_insight_dict_for_delta(insight) for insight in commentary_insights],
            always_present_keys=_PUBLISHED_COMMENTARY_INSIGHTS_DELTA_KEYS,
        )

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
            ready = _delta_ready_rows(
                rows,
                always_present_keys=_projection_keys_for_rows(rows, always_present_keys),
            )
            spark = self._get_spark()
            json_records = [json.dumps(row, default=str) for row in ready]
            rdd = spark.sparkContext.parallelize(json_records)  # type: ignore[attr-defined]
            df = spark.read.json(rdd)  # type: ignore[attr-defined]
            writer = df.write.format("delta").mode("append")  # type: ignore[attr-defined]
            writer.option("mergeSchema", "true").save(uri)
        except ProcessingError:
            raise
        except Exception as error:  # pragma: no cover - library-specific
            raise ProcessingError(
                "spark_delta_write_failed",
                f"failed to write canonical rows to Delta surface {uri} via PySpark",
            ) from error


def _delta_write_mode(uri: str) -> str:
    if uri.startswith("file://"):
        local_path = uri[len("file://") :]
    elif "://" in uri:
        # Remote object stores (gs://, s3://): the ``_delta_log`` can't be stat'd from the
        # local filesystem, so always append. ``write_deltalake`` creates the table on first
        # append, and appending (never overwriting) is what keeps prior events durable.
        return "append"
    else:
        local_path = uri
    delta_log_path = os.path.join(local_path, "_delta_log")
    return "append" if os.path.exists(delta_log_path) else "overwrite"


def _projection_keys_for_rows(
    rows: Sequence[dict[str, object]],
    always_present_keys: frozenset[str] | None,
) -> frozenset[str] | None:
    if always_present_keys != _PUBLISHED_DOCUMENTS_DELTA_KEYS:
        return always_present_keys
    if any(isinstance(row.get("extensions"), dict) and row["extensions"] for row in rows):
        return always_present_keys
    return frozenset(key for key in always_present_keys if key != "extensions")


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
