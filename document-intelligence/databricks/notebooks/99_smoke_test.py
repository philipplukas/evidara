# Databricks notebook source
"""Basic smoke test for Databricks bundle deployment."""

from pyspark.sql import SparkSession


def _get_widget_value(name: str, default: str = "") -> str:
    try:
        return dbutils.widgets.get(name)  # type: ignore[name-defined]
    except Exception:
        return default


spark = SparkSession.builder.getOrCreate()

catalog = _get_widget_value("catalog", "")
if catalog:
    spark.sql("USE CATALOG {catalog}".format(catalog=catalog))
    print({"message": "catalog selected", "catalog": catalog})
else:
    print({"message": "smoke test ran without catalog override"})

print({"status": "ok"})
