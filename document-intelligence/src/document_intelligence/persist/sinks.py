"""Persistence abstractions for canonical output."""

import importlib
import json
import logging
import os
from collections.abc import Callable, Mapping, Sequence
from dataclasses import dataclass, field

import pyarrow as pa
import pyarrow.compute as pc

from document_intelligence.canonical.models import CommentaryInsight, Document, ProcessingManifest, Section
from document_intelligence.errors import ProcessingError

logger = logging.getLogger(__name__)

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
# Columns that exist only on a row nobody publishes: `failure` on a failed result,
# `quarantine` on a withheld one (ADR-0047). They are deliberately NOT in the set above.
#
# `_delta_ready_rows` projects every row to *exactly* `always_present_keys`, so a column
# outside that set is dropped on the way to Delta/Iceberg/Spark whatever the model carries
# — which is how a quarantine reason survived in `InMemoryCanonicalSink` (every test) and
# vanished in every deployed configuration. But putting them in the always-present set is
# not the fix either: on a canonical-ready row both are `None`, PyArrow infers a `null`
# column, and deltalake refuses the whole write with *"Invalid data type for Delta Lake:
# Null"* — that would take the publish path down, not just the reason.
#
# So they are added to the projection **per batch, only when a row carries one**, exactly
# as `extensions` is dropped from it when no row carries one. A present value is a real
# struct, so Arrow types it, and `schema_mode="merge"` evolves the table on first sight.
_PROCESSING_MANIFESTS_CONDITIONAL_KEYS = frozenset({"failure", "quarantine"})
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


def delta_dataset_filesystem(uri: str, storage_options: Mapping[str, str] | None = None) -> object | None:
    """Return a **native** pyarrow filesystem rooted at the Delta table at ``uri`` (#825).

    ``DeltaTable.to_pyarrow_dataset()`` builds its own filesystem when none is passed:
    ``pyarrow.fs.PyFileSystem(DeltaStorageHandler(...))`` — a Python object wrapping the Rust
    object store. Arrow then scans the parquet fragments with ``pre_buffer=True``, so its C++ IO
    thread pool calls *back into Python* through that handler. The bridge is destroyed
    non-deterministically at interpreter shutdown, and when it loses that race the process aborts
    with ``terminate called without an active exception`` — **after** the job has printed its
    summary and returned 0. A Kubernetes Job then reports ``Failed`` (exit 134/139) for a run that
    did exactly what it was asked to do.

    Measured on ``deltalake`` 1.5.0/1.6.2 with ``pyarrow`` 23/24/25 on Python 3.12 and 3.13, over
    both a local-filesystem and a MinIO-backed table: constructing a ``DeltaTable`` is clean
    (0/40 aborts), reading it through ``to_pyarrow_dataset()`` aborts roughly half the time
    (15/30 for the backfill entrypoint itself). Explicitly dropping the dataset and the table and
    forcing a ``gc.collect()`` before exit does *not* help — it makes it marginally more likely,
    because the process then reaches shutdown sooner. Passing a native filesystem removes the
    Python callback from the scan entirely: 0/20 aborts on local, 0/20 on S3.

    **Only the two shapes measured above are taken over**: a local path (bare or ``file://``) and
    ``s3://`` / ``s3a://`` *with an explicit endpoint* in ``storage_options`` — i.e. MinIO, which
    is what the self-hosted deployment runs. Everything else returns ``None`` and keeps
    ``deltalake``'s own handler.

    That allowlist is deliberate, and blanket ``pyarrow.fs.FileSystem.from_uri`` is not a
    substitute for it. pyarrow resolves credentials through the Google/AWS SDK chains while
    ``object_store`` (which ``deltalake`` uses) does not resolve identically: ``from_uri`` happily
    constructs a ``GcsFileSystem`` for ``gs://`` with no GCP credentials present and no error, so a
    surface that reads correctly today would get an unauthorized filesystem and 403 at scan time —
    a hard read failure, not the harmless fallback this function promises. The same divergence
    applies to ``abfs://`` and to real AWS ``s3://`` (``AWS_PROFILE`` / SSO / IMDS). ``from_uri``
    on a bucket URI also costs a network round-trip for region resolution — measured at 4.1 s —
    and ``_open_dataset`` is on the document service's per-request read path.

    Returns ``None`` whenever a native filesystem cannot be built. The caller then passes
    ``filesystem=None`` and ``deltalake`` falls back to its own handler — today's behaviour, which
    reads correctly but can abort at teardown.
    """
    scheme, separator, remainder = uri.partition("://")
    if not separator:
        scheme, remainder = "", uri

    options = storage_options or {}
    endpoint = (options.get("AWS_ENDPOINT_URL") or "").strip()
    if scheme not in {"", "file"} and not (scheme in {"s3", "s3a"} and endpoint):
        # Not a shape this function claims; deltalake's handler stays in charge. Not a warning:
        # nothing is wrong, the allowlist simply does not cover this surface.
        return None

    try:
        import pyarrow.fs as pa_fs

        if scheme in {"", "file"}:
            filesystem, normalized_path = pa_fs.FileSystem.from_uri(uri if scheme else os.path.abspath(uri))
            if not isinstance(filesystem, pa_fs.LocalFileSystem):
                raise TypeError(f"expected a LocalFileSystem for {uri!r}, got {type(filesystem).__name__}")
            return pa_fs.SubTreeFileSystem(normalized_path, filesystem)

        # MinIO / any S3-compatible endpoint: pyarrow will not pick this up from
        # ``storage_options`` (those are ``deltalake``'s), so mirror them explicitly.
        kwargs: dict[str, object] = {
            "endpoint_override": endpoint.split("://", 1)[-1].rstrip("/"),
            # Same ``http://`` prefix test ``delta_storage_options`` uses for AWS_ALLOW_HTTP.
            "scheme": "http" if endpoint.startswith("http://") else "https",
        }
        region = (options.get("AWS_REGION") or "").strip()
        if region:
            kwargs["region"] = region
        access_key_id = (options.get("AWS_ACCESS_KEY_ID") or "").strip()
        secret_access_key = (options.get("AWS_SECRET_ACCESS_KEY") or "").strip()
        if access_key_id and secret_access_key:
            kwargs["access_key"] = access_key_id
            kwargs["secret_key"] = secret_access_key
        # ``to_pyarrow_dataset`` resolves fragment paths relative to the table root, so the
        # filesystem handed to it must be rooted there too.
        return pa_fs.SubTreeFileSystem(remainder.strip("/"), pa_fs.S3FileSystem(**kwargs))
    except Exception:
        # This URI *was* on the allowlist and still could not be resolved — a renamed pyarrow
        # kwarg, a missing backend, a malformed endpoint. Every read then silently reverts to the
        # path that aborts at teardown, while the runbook tells the operator to treat a non-zero
        # exit as real. That must never be a debug-level event.
        logger.warning("delta_native_filesystem_unavailable", extra={"uri": uri}, exc_info=True)
        return None


class CanonicalSink:
    """Persistence interface for canonical writes and emitted events."""

    def persist(
        self,
        document: Document,
        sections: list[Section],
        manifest: ProcessingManifest,
    ) -> None:
        raise NotImplementedError

    def persist_quarantine(self, manifest: ProcessingManifest) -> None:
        """Record a quarantined result: the manifest row only, no canonical rows (ADR-0047).

        The whole point is that no document and no sections are published — but the
        judgment is still written down, with its reason, where an operator can group the
        queue by it. A quarantine that leaves no row is silent failure with extra steps.
        """
        raise NotImplementedError

    def record_status_events(self, status_events: list[dict[str, object]]) -> None:
        raise NotImplementedError

    def record_document_processed_event(self, document_processed_event: dict[str, object]) -> None:
        raise NotImplementedError

    def persist_commentary_insights(self, commentary_insights: list[CommentaryInsight]) -> None:
        raise NotImplementedError

    def latest_document_revision(self, document_id: str) -> int | None:
        """Highest ``document_revision`` already published for ``document_id``, if known (#652).

        The pipeline uses this to publish a re-acquisition as revision *N+1* rather than
        pinning every publication at 1. ``None`` means "no history available" — either the
        document is new or this sink cannot read back — and the caller starts at 1.

        Defaulting to ``None`` keeps sinks that cannot read (Iceberg, Spark) behaving exactly
        as they do today instead of failing the write path over a missing read capability.
        """
        return None


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

    def persist_quarantine(self, manifest: ProcessingManifest) -> None:
        self.processing_manifests.append(manifest)

    def record_status_events(self, status_events: list[dict[str, object]]) -> None:
        self.status_events.extend(status_events)

    def record_document_processed_event(self, document_processed_event: dict[str, object]) -> None:
        self.document_processed_events.append(document_processed_event)

    def persist_commentary_insights(self, commentary_insights: list[CommentaryInsight]) -> None:
        self.published_commentary_insights.extend(commentary_insights)

    def latest_document_revision(self, document_id: str) -> int | None:
        revisions = [
            document.document_revision
            for document in self.published_documents
            if document.document_id == document_id and document.document_revision is not None
        ]
        return max(revisions) if revisions else None


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

    def persist_quarantine(self, manifest: ProcessingManifest) -> None:
        """Write the manifest row alone — no document, no sections (ADR-0047)."""
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

    def latest_document_revision(self, document_id: str) -> int | None:
        """Read back the highest revision already published for ``document_id`` (#652).

        Pushes the ``document_id`` predicate and the single column down into the scan, so
        this stays a metadata-pruned read of one column rather than a corpus-wide load.

        Never raises: a missing table (first publication of anything), an absent
        ``deltalake``, or an unreadable surface all mean "no history", and the caller then
        starts at revision 1. Failing the write path because history could not be read
        would turn a degraded read into a dropped document, which is the worse outcome.
        """
        try:
            deltalake_mod = importlib.import_module("deltalake")
            table_kwargs = {"storage_options": self._storage_options} if self._storage_options else {}
            dataset = deltalake_mod.DeltaTable(
                self._config.published_documents_uri, **table_kwargs
            ).to_pyarrow_dataset()
            if "document_revision" not in dataset.schema.names:
                return None
            table = dataset.to_table(
                columns=["document_revision"],
                filter=pc.field("document_id") == document_id,
            )
        except Exception as error:
            # The surface not existing yet is the ordinary first-publication case, not a
            # fault; only genuinely unexpected read failures are worth a warning.
            if not _is_missing_delta_table(error):
                logger.warning(
                    "latest_document_revision_unavailable",
                    extra={"document_id": document_id},
                    exc_info=True,
                )
            return None
        revisions = [value for value in table.column("document_revision").to_pylist() if value is not None]
        return max(revisions) if revisions else None

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
                schema = _widen_for_new_nested_fields(schema, ready)
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


def _is_missing_delta_table(error: BaseException) -> bool:
    """Whether ``error`` means "this Delta surface does not exist yet" (#652).

    Matched on the exception *name* rather than the type: ``TableNotFoundError`` lives in
    ``deltalake._internal``, a native module, so importing it here to catch it would couple
    canonical persistence to a private path that has moved between deltalake releases.
    """
    return type(error).__name__ == "TableNotFoundError"


def _default_delta_writer() -> Callable[..., object]:
    try:
        deltalake_module = importlib.import_module("deltalake")
    except ModuleNotFoundError as error:  # pragma: no cover - depends on env
        raise ProcessingError(
            "missing_delta_dependency",
            "deltalake is required for Delta-backed canonical persistence",
        ) from error
    return deltalake_module.write_deltalake


@dataclass(frozen=True)
class IcebergSinkConfig:
    """Catalog-addressed canonical surfaces (ADR-0036).

    The Delta config names each surface by *URI*; this names it by **table** in a
    catalog (``namespace.table``), which is the whole point of the move: consumers
    resolve surfaces through the catalog and can query them with SQL, instead of
    every reader hardcoding a storage path.
    """

    namespace: str = "evidara"
    published_documents_table: str = "published_documents"
    published_sections_table: str = "published_sections"
    processing_manifests_table: str = "processing_manifests"
    published_commentary_insights_table: str | None = "published_commentary_insights"
    catalog_name: str = "nessie"
    catalog_properties: Mapping[str, str] = field(default_factory=dict)

    @classmethod
    def from_environment(cls, environ: Mapping[str, str] | None = None) -> "IcebergSinkConfig | None":
        """Build the config from env, or ``None`` when no catalog is configured.

        Storage credentials reuse the ``DI_S3_*`` vars the bundle loader already
        uses, so one set of MinIO/S3 settings serves both reads and writes.
        """
        env = os.environ if environ is None else environ
        uri = (env.get("DI_ICEBERG_CATALOG_URI") or "").strip()
        if not uri:
            return None

        properties: dict[str, str] = {"type": "rest", "uri": uri}
        warehouse = (env.get("DI_ICEBERG_WAREHOUSE") or "").strip()
        if warehouse:
            properties["warehouse"] = warehouse
        s3_endpoint = (env.get("DI_S3_ENDPOINT_URL") or "").strip()
        if s3_endpoint:
            properties["s3.endpoint"] = s3_endpoint
            # Path-style is required for MinIO and harmless elsewhere.
            properties["s3.path-style-access"] = "true"
        access_key = (env.get("DI_S3_ACCESS_KEY_ID") or "").strip()
        secret_key = (env.get("DI_S3_SECRET_ACCESS_KEY") or "").strip()
        if access_key and secret_key:
            properties["s3.access-key-id"] = access_key
            properties["s3.secret-access-key"] = secret_key
        region = (env.get("DI_S3_REGION") or "").strip()
        if region:
            properties["s3.region"] = region

        return cls(
            namespace=(env.get("DI_ICEBERG_NAMESPACE") or "evidara").strip(),
            catalog_name=(env.get("DI_ICEBERG_CATALOG_NAME") or "nessie").strip(),
            catalog_properties=properties,
        )


class IcebergCanonicalSink(CanonicalSink):
    """Append canonical rows to Iceberg tables registered in a catalog (ADR-0036).

    Deliberately mirrors :class:`DeltaCanonicalSink`: identical canonical row
    shapes and the same normalisation helpers — only the *destination* changes,
    from a hardcoded table URI to a named table in a catalog (Nessie), which is
    what lets Trino/SQL read the surfaces without any delta-rs coupling.
    """

    def __init__(
        self,
        config: IcebergSinkConfig,
        *,
        catalog: object | None = None,
    ) -> None:
        self._config = config
        self._catalog = catalog
        self.status_events: list[dict[str, object]] = []
        self.document_processed_events: list[dict[str, object]] = []

    def persist(
        self,
        document: Document,
        sections: list[Section],
        manifest: ProcessingManifest,
    ) -> None:
        self._write_rows(
            self._config.published_documents_table,
            [_document_dict_for_delta(document)],
            always_present_keys=_PUBLISHED_DOCUMENTS_DELTA_KEYS,
        )
        # Mirrors the Delta sink: published surfaces predate `parent_section_id`.
        section_rows = []
        for section in sections:
            row = section.to_dict()
            row.pop("parent_section_id", None)
            section_rows.append(row)
        self._write_rows(
            self._config.published_sections_table,
            section_rows,
            always_present_keys=_PUBLISHED_SECTIONS_DELTA_KEYS,
        )
        self._write_rows(
            self._config.processing_manifests_table,
            [_manifest_dict_for_delta(manifest)],
            always_present_keys=_PROCESSING_MANIFESTS_DELTA_KEYS,
        )

    def persist_quarantine(self, manifest: ProcessingManifest) -> None:
        """Write the manifest row alone — no document, no sections (ADR-0047)."""
        self._write_rows(
            self._config.processing_manifests_table,
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
        if not self._config.published_commentary_insights_table:
            raise ProcessingError(
                "missing_commentary_insights_surface",
                "published commentary insights table is required when commentary insights are emitted",
            )
        self._write_rows(
            self._config.published_commentary_insights_table,
            [_commentary_insight_dict_for_delta(insight) for insight in commentary_insights],
            always_present_keys=_PUBLISHED_COMMENTARY_INSIGHTS_DELTA_KEYS,
            schema_override=_COMMENTARY_INSIGHTS_ARROW_SCHEMA,
        )

    def _load_catalog(self) -> object:
        if self._catalog is None:
            try:
                catalog_module = importlib.import_module("pyiceberg.catalog")
            except ModuleNotFoundError as error:  # pragma: no cover - depends on env
                raise ProcessingError(
                    "missing_iceberg_dependency",
                    "pyiceberg is required for Iceberg-backed canonical persistence",
                ) from error
            self._catalog = catalog_module.load_catalog(
                self._config.catalog_name, **dict(self._config.catalog_properties)
            )
        return self._catalog

    def _write_rows(
        self,
        table_name: str,
        rows: Sequence[dict[str, object]],
        *,
        always_present_keys: frozenset[str] | None = None,
        schema_override: pa.Schema | None = None,
    ) -> None:
        if not rows:
            return
        identifier = f"{self._config.namespace}.{table_name}"
        try:
            ready = _delta_ready_rows(
                rows,
                always_present_keys=_projection_keys_for_rows(rows, always_present_keys),
            )
            catalog = self._load_catalog()
            catalog.create_namespace_if_not_exists(self._config.namespace)

            if catalog.table_exists(identifier):
                table = catalog.load_table(identifier)
                # Conform to the table's committed schema so appends stay valid as
                # canonical shapes evolve; fall back to inference when a new column
                # is present (the catalog rejects it loudly rather than silently).
                #
                # That stated policy — loudly, never silently — only ever held for
                # *top-level* columns (#871). `pa.Table.from_pylist(rows, schema=...)` also
                # applies the target type to nested ones, and it drops a struct field
                # the target struct does not declare without raising. So a new key
                # inside `metadata` (or any optional `provenance` field) took the
                # silent path the comment above rules out. Widen first, exactly as the
                # Delta sink does: the batch then reaches the catalog with its true
                # shape, and the catalog decides — loudly — whether to evolve.
                arrow_schema = _widen_for_new_nested_fields(table.schema().as_arrow(), ready)
                incoming = {key for row in ready for key in row}
                schema = arrow_schema if incoming.issubset(set(arrow_schema.names)) else None
            else:
                schema = schema_override
                table = None

            arrow_table = (
                pa.Table.from_pylist(ready, schema=schema) if schema is not None else pa.Table.from_pylist(ready)
            )
            if table is None:
                table = catalog.create_table(identifier, schema=arrow_table.schema)
            table.append(arrow_table)
        except ProcessingError:
            raise
        except Exception as error:  # pragma: no cover - library-specific
            raise ProcessingError(
                "iceberg_write_failed",
                f"failed to write canonical rows to Iceberg table {identifier}",
            ) from error


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

    def persist_quarantine(self, manifest: ProcessingManifest) -> None:
        """Write the manifest row alone — no document, no sections (ADR-0047)."""
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
    if always_present_keys == _PUBLISHED_DOCUMENTS_DELTA_KEYS:
        if any(isinstance(row.get("extensions"), dict) and row["extensions"] for row in rows):
            return always_present_keys
        return frozenset(key for key in always_present_keys if key != "extensions")
    if always_present_keys == _PROCESSING_MANIFESTS_DELTA_KEYS:
        # Widen, rather than narrow: `failure` and `quarantine` join the projection only for
        # a batch that actually carries one. Forcing them always-present would write a
        # PyArrow `null` column on every canonical-ready row, which deltalake rejects
        # outright ("Invalid data type for Delta Lake: Null") — taking down the publish path
        # to preserve a reason. Leaving them out entirely is what silently discarded the
        # quarantine slug in every non-in-memory sink. See the constant's comment.
        present = frozenset(
            key
            for key in _PROCESSING_MANIFESTS_CONDITIONAL_KEYS
            if any(isinstance(row.get(key), dict) and row[key] for row in rows)
        )
        return always_present_keys | present
    return always_present_keys


def _widen_for_new_nested_fields(schema: pa.Schema, rows: list[dict[str, object]]) -> pa.Schema:
    """Add struct fields the batch carries but the existing table's schema does not (#836).

    Append reads the table's own Arrow schema and casts the batch to it, which is what keeps
    a narrowed batch compatible with a legacy surface. But that cast is applied to *nested*
    types too, and PyArrow drops a struct field the target type does not declare — silently,
    with no error. ``metadata`` is one struct column, so every canonical metadata key added
    after a table was created (``official_citation``, ``in_force_from``, now ``regeste``) is
    written on a fresh table and dropped on every append to an existing one. The value is
    then absent from Delta, absent from the lean document, and absent from the projection,
    while every test — which starts from an empty directory — passes.

    ``metadata`` is only the loudest case. The loss is a property of **every struct column**
    on every canonical surface: `provenance` is one too, and ``Provenance.to_dict`` omits its
    optional fields when they are ``None``, so the struct a table is created with is whatever
    the *first* row happened to carry — an optional field absent from that row is then dropped
    from every row after it. Which also means the exposure is not "keys added after the table
    was created"; it is "keys absent from the batch that created the table".

    ``schema_mode="merge"`` cannot rescue it: by the time ``write_deltalake`` sees the batch,
    the field is already gone. So unify the existing schema with the one inferred from the
    batch *before* the cast. Unification is permissive in one direction only in practice:
    a column that is null across the whole batch infers ``null`` and unifies to the existing
    type, which is the narrowing this function must not undo.

    Falls back to the existing schema whenever unification is not possible — a genuine type
    conflict between the batch and the table is not something to paper over here; the cast
    then behaves exactly as it did before.
    """
    try:
        inferred = pa.Table.from_pylist(rows).schema
    except Exception:
        logger.debug("delta_schema_infer_skipped", exc_info=True)
        return schema

    # Unify PER FIELD, not the whole schema at once (#871, second route).
    #
    # `pa.unify_schemas` is all-or-nothing: it raises on the first incompatible
    # column and the caller then keeps the un-widened schema for EVERY column.
    # `published_commentary_insights` hits that on every single write —
    # `metadata` is declared `map<string, string>` while `from_pylist` infers
    # `struct<...>` from the Python dict, so unification raises
    #
    #     Unable to merge: Field metadata has incompatible types:
    #     map<string, string> vs struct<extractive: string>
    #
    # ...and `generator`, `support`, `referenced_authorities` and `scores` all
    # silently lose their new nested fields as collateral. Struct widening was
    # never broken; one map-typed column was poisoning it.
    #
    # Per field, an incompatible column falls back to its declared type — which
    # is exactly the pre-existing behaviour for that column — and every other
    # column still widens.
    merged_fields: list[pa.Field] = []
    for declared in schema:
        if declared.name not in inferred.names:
            merged_fields.append(declared)
            continue
        try:
            unified_field = pa.unify_schemas(
                [pa.schema([declared]), pa.schema([inferred.field(declared.name)])],
                promote_options="permissive",
            ).field(declared.name)
        except Exception:
            # A genuine type conflict between batch and table is not something to
            # paper over here; the cast then behaves exactly as it did before.
            #
            # `%s`, not a `field=` kwarg: this is a stdlib logger, and a stray keyword
            # makes `Logger._log()` raise `TypeError` — but only once someone turns the
            # level up to DEBUG, which is precisely what you do to find out why a field
            # was not widened. The raise happens inside `_write_rows`' outer `except`,
            # so it does not surface as a logging fault: it becomes
            # `delta_write_failed`, and the whole publish of
            # `published_commentary_insights` — the one surface that takes this branch
            # on *every* write, because its `metadata` is a declared map — goes down.
            # A conservative fallback that is fatal under debug logging is not a
            # fallback. See `test_the_unify_fallback_survives_debug_logging`.
            logger.debug("delta_schema_field_unify_skipped field=%s", declared.name, exc_info=True)
            merged_fields.append(declared)
            continue
        merged_fields.append(unified_field)

    # Never introduce a *top-level* column from inside a widening helper: only
    # fields already declared by `schema` are carried above, so the surface can
    # gain nested fields but not columns. The Delta sink has already established
    # the batch's keys are a subset of the table's; the Iceberg sink checks
    # afterwards and drops to inference, which is how a new column reaches its
    # catalog loudly.
    return pa.schema(merged_fields)


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
