# Databricks notebook source
"""Bootstrap bronze + published DDL for document-intelligence.

Runs the rendered DDL from both bootstrap modules against the target catalog.

Widgets:
  catalog            - Unity Catalog name (required).
  surfaces_root_uri  - Root GCS URI used for published surface LOCATION clauses (required).
  bronze_schema      - Schema for bronze Auto Loader tables (default "bronze").
  published_schema   - Schema for published surface registrations (default "published").

Run this notebook before the first ``dbt run`` in a fresh workspace, and after
schema contract changes to bronze_schemas.py or persist/surfaces.py. Statements
are idempotent (CREATE SCHEMA / TABLE IF NOT EXISTS), so re-running is safe.
"""

from pyspark.sql import SparkSession

from document_intelligence.bootstrap.bronze_schemas import render_register_bronze_sql
from document_intelligence.bootstrap.register_surfaces import render_register_surfaces_sql


def _widget(name: str, default: str = "") -> str:
    try:
        return dbutils.widgets.get(name)  # type: ignore[name-defined]
    except Exception:
        return default


def _execute(spark: SparkSession, sql_script: str) -> None:
    for raw_statement in sql_script.split(";"):
        statement = raw_statement.strip()
        if not statement or statement.startswith("--"):
            continue
        spark.sql(statement)


spark = SparkSession.builder.getOrCreate()

catalog = _widget("catalog")
surfaces_root_uri = _widget("surfaces_root_uri")
bronze_schema = _widget("bronze_schema") or "bronze"
published_schema = _widget("published_schema") or "published"

if not catalog:
    raise ValueError("catalog widget is required")
if not surfaces_root_uri:
    raise ValueError("surfaces_root_uri widget is required")

bronze_sql = render_register_bronze_sql(catalog_name=catalog, schema_name=bronze_schema)
published_sql = render_register_surfaces_sql(
    catalog_name=catalog,
    schema_name=published_schema,
    surfaces_root_uri=surfaces_root_uri,
)

print({"step": "bronze", "catalog": catalog, "schema": bronze_schema, "status": "starting"})
_execute(spark, bronze_sql)
print({"step": "bronze", "status": "completed"})

print({"step": "published", "catalog": catalog, "schema": published_schema, "status": "starting"})
_execute(spark, published_sql)
print({"step": "published", "status": "completed"})
