"""Bronze Delta table definitions for document-intelligence.

The bronze layer lands raw JSON drops via Auto Loader. All payload columns are
typed ``STRING`` here so schema inference from cloudFiles never conflicts with
the pre-declared table shape; dbt staging models cast to typed columns
downstream. Only the Auto Loader bookkeeping columns (``ingested_at``,
``_source_file``) carry narrower types.
"""

from collections.abc import Iterable
from dataclasses import dataclass


@dataclass(frozen=True)
class BronzeColumn:
    name: str
    sql_type: str
    description: str


@dataclass(frozen=True)
class BronzeTableDefinition:
    table_name: str
    description: str
    columns: tuple[BronzeColumn, ...]
    loaded_at_column: str = "ingested_at"


_AUTOLOADER_COLUMNS: tuple[BronzeColumn, ...] = (
    BronzeColumn("ingested_at", "TIMESTAMP", "Auto Loader ingest timestamp."),
    BronzeColumn("_source_file", "STRING", "Source file URI emitted by input_file_name()."),
)


LANDING_ENVELOPES = BronzeTableDefinition(
    table_name="landing_envelopes",
    description="Crawl envelope records describing candidate documents landed from upstream ingestion.",
    columns=(
        BronzeColumn("ingestion_id", "STRING", "Idempotent envelope identifier."),
        BronzeColumn("crawl_run_id", "STRING", "Crawl run that produced the envelope."),
        BronzeColumn("source_system", "STRING", "Upstream source system name."),
        BronzeColumn("source_uri", "STRING", "Canonical source URI."),
        BronzeColumn("retrieved_at", "STRING", "ISO-8601 retrieval timestamp (cast in staging)."),
        BronzeColumn("content_type", "STRING", "HTTP Content-Type reported by the source."),
        BronzeColumn("raw_object_uri", "STRING", "GCS URI of the raw payload object."),
        BronzeColumn("checksum", "STRING", "SHA-256 checksum of the raw payload."),
        BronzeColumn("http_status", "STRING", "HTTP status code (cast in staging)."),
        BronzeColumn("artifact_type", "STRING", "Artifact kind emitted by the crawler."),
        BronzeColumn("title", "STRING", "Envelope-declared title."),
        BronzeColumn("language", "STRING", "Declared or detected language."),
        BronzeColumn("source_document_id", "STRING", "Stable source-side document identifier."),
        BronzeColumn("country", "STRING", "Country code."),
        BronzeColumn("jurisdiction", "STRING", "Jurisdiction code."),
        BronzeColumn("document_class", "STRING", "Declared document class."),
        BronzeColumn("authority_name", "STRING", "Issuing authority name."),
        BronzeColumn("authority_type", "STRING", "Issuing authority type."),
        BronzeColumn("court_name", "STRING", "Court name when applicable."),
        BronzeColumn("court_level", "STRING", "Court level when applicable."),
        BronzeColumn("parent_uri", "STRING", "Referrer URI for discovered links."),
        BronzeColumn("discovery_depth", "STRING", "Crawl depth (cast in staging)."),
        BronzeColumn("source_metadata", "STRING", "Raw JSON source metadata payload."),
        BronzeColumn("envelope_schema_version", "STRING", "Envelope schema version."),
        BronzeColumn("adapter_version", "STRING", "Adapter version that produced the envelope."),
        *_AUTOLOADER_COLUMNS,
    ),
    loaded_at_column="retrieved_at",
)


DOCUMENT_PROCESSING_EVENTS = BronzeTableDefinition(
    table_name="document_processing_events",
    description="Processing lifecycle events emitted by the document-intelligence runtime.",
    columns=(
        BronzeColumn("event_id", "STRING", "Unique event identifier."),
        BronzeColumn("document_version_id", "STRING", "Document version the event pertains to."),
        BronzeColumn("ingestion_id", "STRING", "Triggering ingestion identifier."),
        BronzeColumn("stage", "STRING", "Pipeline stage name."),
        BronzeColumn("event_type", "STRING", "Event type (started, succeeded, failed, dead_letter)."),
        BronzeColumn("attempt_number", "STRING", "Retry attempt number (cast in staging)."),
        BronzeColumn("event_timestamp", "STRING", "ISO-8601 event timestamp (cast in staging)."),
        BronzeColumn("error_type", "STRING", "Error classification when event_type is failed."),
        BronzeColumn("error_message", "STRING", "Error detail when event_type is failed."),
        BronzeColumn("artifact_uri", "STRING", "Artifact URI associated with the event."),
        BronzeColumn("event_metadata", "STRING", "Event-specific JSON metadata payload."),
        *_AUTOLOADER_COLUMNS,
    ),
    loaded_at_column="event_timestamp",
)


RAW_DOCLING_OUTPUT = BronzeTableDefinition(
    table_name="raw_docling_output",
    description="Raw Docling parser output, one row per parsed document version.",
    columns=(
        BronzeColumn("document_version_id", "STRING", "Canonical document version identifier."),
        BronzeColumn("file_id", "STRING", "Fallback file identifier when version is absent."),
        BronzeColumn("processed_at", "STRING", "ISO-8601 parse timestamp (cast in staging)."),
        BronzeColumn("policy_set_id", "STRING", "Parser policy set applied during extraction."),
        BronzeColumn("docling_json", "STRING", "Serialised Docling document JSON payload."),
        *_AUTOLOADER_COLUMNS,
    ),
)


RAW_NLP_ANNOTATIONS = BronzeTableDefinition(
    table_name="raw_nlp_annotations",
    description="Raw NLP annotation payloads (entities, relations) produced per document section.",
    columns=(
        BronzeColumn("document_version_id", "STRING", "Document version identifier."),
        BronzeColumn("file_id", "STRING", "Fallback file identifier when version is absent."),
        BronzeColumn("section_idx", "STRING", "Section index within the document (cast in staging)."),
        BronzeColumn("model_name", "STRING", "NLP model name."),
        BronzeColumn("nlp_policy_id", "STRING", "NLP policy set identifier."),
        BronzeColumn("processed_at", "STRING", "ISO-8601 annotation timestamp (cast in staging)."),
        BronzeColumn("entities_json", "STRING", "Serialised entity array JSON payload."),
        BronzeColumn("relations_json", "STRING", "Serialised relation array JSON payload."),
        *_AUTOLOADER_COLUMNS,
    ),
)


RAW_METADATA = BronzeTableDefinition(
    table_name="raw_metadata",
    description="Optional external metadata enrichments landed alongside raw documents.",
    columns=(
        BronzeColumn("document_version_id", "STRING", "Document version identifier."),
        BronzeColumn("source", "STRING", "Upstream metadata source name."),
        BronzeColumn("metadata_json", "STRING", "Serialised metadata JSON payload."),
        BronzeColumn("processed_at", "STRING", "ISO-8601 enrichment timestamp (cast in staging)."),
        *_AUTOLOADER_COLUMNS,
    ),
)


RAW_DOCUMENTS = BronzeTableDefinition(
    table_name="raw_documents",
    description="Optional landing surface for unstructured document payloads (reserved).",
    columns=(
        BronzeColumn("document_version_id", "STRING", "Document version identifier."),
        BronzeColumn("payload", "STRING", "Raw document payload (text, html, xml)."),
        BronzeColumn("content_type", "STRING", "MIME content type of the payload."),
        *_AUTOLOADER_COLUMNS,
    ),
)


BRONZE_TABLE_DEFINITIONS: dict[str, BronzeTableDefinition] = {
    definition.table_name: definition
    for definition in (
        LANDING_ENVELOPES,
        DOCUMENT_PROCESSING_EVENTS,
        RAW_DOCLING_OUTPUT,
        RAW_NLP_ANNOTATIONS,
        RAW_METADATA,
        RAW_DOCUMENTS,
    )
}


_BRONZE_TABLE_PROPERTIES: tuple[tuple[str, str], ...] = (
    ("delta.columnMapping.mode", "name"),
    ("delta.minReaderVersion", "2"),
    ("delta.minWriterVersion", "5"),
    ("delta.enableChangeDataFeed", "true"),
)


def iter_bronze_table_definitions() -> Iterable[BronzeTableDefinition]:
    return BRONZE_TABLE_DEFINITIONS.values()


def get_bronze_table_definition(table_name: str) -> BronzeTableDefinition:
    return BRONZE_TABLE_DEFINITIONS[table_name]


def render_register_bronze_sql(*, catalog_name: str, schema_name: str = "bronze") -> str:
    """Render idempotent SQL that creates the bronze schema and its Delta tables."""

    statements: list[str] = [
        "-- Register document-intelligence bronze landing tables in Unity Catalog.",
        "-- Safe to run repeatedly; CREATE TABLE IF NOT EXISTS is used throughout.",
        f"CREATE SCHEMA IF NOT EXISTS `{catalog_name}`.`{schema_name}`;",
        "",
    ]

    properties_sql = ",\n".join(f"  '{key}' = '{value}'" for key, value in _BRONZE_TABLE_PROPERTIES)

    for definition in iter_bronze_table_definitions():
        columns_sql = ",\n".join(f"  `{column.name}` {column.sql_type}" for column in definition.columns)
        statements.extend(
            [
                f"-- {definition.description}",
                f"CREATE TABLE IF NOT EXISTS `{catalog_name}`.`{schema_name}`.`{definition.table_name}` (",
                columns_sql,
                ")",
                "USING DELTA",
                "TBLPROPERTIES (",
                properties_sql,
                ");",
                "",
            ]
        )

    return "\n".join(statements).rstrip() + "\n"
