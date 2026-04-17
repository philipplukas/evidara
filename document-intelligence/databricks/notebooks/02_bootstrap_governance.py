# Databricks notebook source
"""Apply Unity Catalog grants and PII column tags for document-intelligence.

Executes the SQL rendered by document_intelligence.bootstrap.governance.
Idempotent: GRANT and ALTER TABLE SET TAGS re-run cleanly.

Widgets:
  catalog        - Unity Catalog name (required).
  mode           - grants | tags | all (default: all).
"""

from pyspark.sql import SparkSession

from document_intelligence.bootstrap.governance import (
    render_column_tags_sql,
    render_grants_sql,
)
from document_intelligence.bootstrap.sql_exec import execute_sql_script


def _widget(name: str, default: str = "") -> str:
    try:
        return dbutils.widgets.get(name)  # type: ignore[name-defined]
    except Exception:
        return default


spark = SparkSession.builder.getOrCreate()

catalog = _widget("catalog")
mode = _widget("mode") or "all"

if not catalog:
    raise ValueError("catalog widget is required")

if mode in ("grants", "all"):
    print({"step": "grants", "catalog": catalog, "status": "starting"})
    execute_sql_script(spark, render_grants_sql(catalog_name=catalog))
    print({"step": "grants", "status": "completed"})

if mode in ("tags", "all"):
    print({"step": "tags", "catalog": catalog, "status": "starting"})
    execute_sql_script(spark, render_column_tags_sql(catalog_name=catalog))
    print({"step": "tags", "status": "completed"})
