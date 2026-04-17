# Databricks notebook source
"""Auto Loader bronze ingestion for document-intelligence.

Reads newline-delimited JSON drops from GCS under

  ${gcs_processed_bucket}/{landing_envelopes,processing_events,docling,nlp}/**

and appends them into bronze Delta tables in Unity Catalog:

  ${catalog}.bronze.landing_envelopes
  ${catalog}.bronze.document_processing_events
  ${catalog}.bronze.raw_docling_output
  ${catalog}.bronze.raw_nlp_annotations

Each stream runs with trigger(availableNow=True) so the notebook completes
after processing currently-available files and can be scheduled as a batch
job. Schema evolution is handled by the sink (``mergeSchema=true``); all
cloud-loaded columns land as STRING (``cloudFiles.inferColumnTypes=false``)
and are cast by the dbt staging layer. One ``cloudFiles.schemaLocation`` and
one ``checkpointLocation`` is maintained per stream under
``${gcs_processed_bucket}/_schemas`` and ``_checkpoints`` respectively.
"""

from dataclasses import dataclass

from pyspark.sql import SparkSession
from pyspark.sql.functions import current_timestamp, input_file_name


def _widget(name: str, default: str = "") -> str:
    try:
        return dbutils.widgets.get(name)  # type: ignore[name-defined]
    except Exception:
        return default


@dataclass(frozen=True)
class BronzeStream:
    source_subpath: str
    target_table: str


STREAMS: tuple[BronzeStream, ...] = (
    BronzeStream("landing_envelopes", "bronze.landing_envelopes"),
    BronzeStream("processing_events", "bronze.document_processing_events"),
    BronzeStream("docling", "bronze.raw_docling_output"),
    BronzeStream("nlp", "bronze.raw_nlp_annotations"),
)


spark = SparkSession.builder.getOrCreate()

catalog = _widget("catalog")
bucket = _widget("gcs_processed_bucket").rstrip("/")
schema_root = _widget("schema_root") or f"{bucket}/_schemas"
checkpoint_root = _widget("checkpoint_root") or f"{bucket}/_checkpoints"

if not catalog or not bucket:
    raise ValueError("catalog and gcs_processed_bucket are required")


def _ingest(stream: BronzeStream) -> None:
    source_path = f"{bucket}/{stream.source_subpath}/"
    schema_location = f"{schema_root}/{stream.source_subpath}"
    checkpoint_location = f"{checkpoint_root}/{stream.source_subpath}"
    target = f"`{catalog}`.{stream.target_table}"

    reader = (
        spark.readStream.format("cloudFiles")
        .option("cloudFiles.format", "json")
        .option("cloudFiles.schemaLocation", schema_location)
        .option("cloudFiles.inferColumnTypes", "false")
        .option("cloudFiles.schemaEvolutionMode", "addNewColumns")
        .option("multiLine", "true")
    )

    df = (
        reader.load(source_path)
        .withColumn("_source_file", input_file_name())
        .withColumn("ingested_at", current_timestamp())
    )

    (
        df.writeStream.format("delta")
        .option("checkpointLocation", checkpoint_location)
        .option("mergeSchema", "true")
        .outputMode("append")
        .trigger(availableNow=True)
        .toTable(target)
        .awaitTermination()
    )


for stream in STREAMS:
    print({"stream": stream.source_subpath, "target": stream.target_table, "status": "starting"})
    _ingest(stream)
    print({"stream": stream.source_subpath, "target": stream.target_table, "status": "completed"})
