# Databricks notebook source
"""Bootstrap notebook for bronze Auto Loader ingestion.

This notebook intentionally performs only minimal validation and emits the
resolved paths. The production ingestion logic can evolve here without changing
bundle wiring.
"""

from pyspark.sql import SparkSession


def _get_widget_value(name: str, default: str = "") -> str:
    try:
        return dbutils.widgets.get(name)  # type: ignore[name-defined]
    except Exception:
        return default


spark = SparkSession.builder.getOrCreate()

catalog = _get_widget_value("catalog", "doc_intel_dev")
gcs_processed_bucket = _get_widget_value("gcs_processed_bucket", "")

if not gcs_processed_bucket:
    raise ValueError("gcs_processed_bucket is required")

print(
    {
        "message": "autoloader bootstrap",
        "catalog": catalog,
        "gcs_processed_bucket": gcs_processed_bucket,
    }
)
