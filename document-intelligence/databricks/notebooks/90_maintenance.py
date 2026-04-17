# Databricks notebook source
"""Scheduled OPTIMIZE and VACUUM for document-intelligence Delta tables.

Runs OPTIMIZE (file compaction) on every bronze/marts table and VACUUM with
168-hour retention (7 days, the Databricks default) on tables where time
travel past that window is unnecessary. Does NOT touch snapshots or the
published external tables - those are retained longer for audit.
"""

from pyspark.sql import SparkSession


def _widget(name: str, default: str = "") -> str:
    try:
        return dbutils.widgets.get(name)  # type: ignore[name-defined]
    except Exception:
        return default


spark = SparkSession.builder.getOrCreate()

catalog = _widget("catalog")
vacuum_retention_hours = int(_widget("vacuum_retention_hours") or "168")

if not catalog:
    raise ValueError("catalog widget is required")


BRONZE_TABLES: tuple[str, ...] = (
    "landing_envelopes",
    "document_processing_events",
    "raw_docling_output",
    "raw_nlp_annotations",
    "raw_metadata",
    "raw_documents",
)

MART_TABLES: tuple[str, ...] = (
    "fct_document_processing",
    "document_knowledge_base",
    "embeddings_ready",
    "srv_search_documents",
    "srv_search_chunks",
    "analytics_mart",
    "dim_document",
    "dim_source_system",
    "dim_jurisdiction",
)


def _run(statement: str) -> None:
    print({"op": "sql", "statement": statement})
    spark.sql(statement)


for table in BRONZE_TABLES:
    fq = f"`{catalog}`.bronze.`{table}`"
    _run(f"OPTIMIZE {fq}")
    _run(f"VACUUM {fq} RETAIN {vacuum_retention_hours} HOURS")

for table in MART_TABLES:
    fq = f"`{catalog}`.di_marts.`{table}`"
    _run(f"OPTIMIZE {fq}")
    _run(f"VACUUM {fq} RETAIN {vacuum_retention_hours} HOURS")

print({"status": "maintenance_completed"})
