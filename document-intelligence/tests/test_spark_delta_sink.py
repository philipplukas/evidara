"""Tests for SparkDeltaCanonicalSink using a mocked SparkSession."""

import json
import os
import sys
import unittest
from unittest.mock import MagicMock, call, patch

sys.path.insert(0, os.path.join(os.path.dirname(__file__), "..", "src"))
sys.path.insert(0, os.path.dirname(__file__))

from document_intelligence.errors import ProcessingError
from document_intelligence.persist.sinks import (
    DeltaSinkConfig,
    SparkDeltaCanonicalSink,
)
from support import build_bundle_event, build_manifest_payload
from test_adapters import build_commentary_insight


def _make_mock_spark() -> MagicMock:
    """Build a minimal mock SparkSession with the APIs used by SparkDeltaCanonicalSink."""
    spark = MagicMock(name="SparkSession")
    mock_rdd = MagicMock(name="RDD")
    mock_df = MagicMock(name="DataFrame")
    mock_write = MagicMock(name="DataFrameWriter")

    spark.sparkContext.parallelize.return_value = mock_rdd
    spark.read.json.return_value = mock_df
    mock_df.write = mock_write
    mock_write.format.return_value = mock_write
    mock_write.mode.return_value = mock_write
    mock_write.option.return_value = mock_write
    mock_write.save.return_value = None

    return spark


class SparkDeltaCanonicalSinkTests(unittest.TestCase):
    def _make_sink(self) -> tuple["SparkDeltaCanonicalSink", MagicMock]:
        config = DeltaSinkConfig(
            published_documents_uri="gs://bucket/published_documents",
            published_sections_uri="gs://bucket/published_sections",
            processing_manifests_uri="gs://bucket/processing_manifests",
            published_commentary_insights_uri="gs://bucket/published_commentary_insights",
        )
        spark = _make_mock_spark()
        sink = SparkDeltaCanonicalSink(config, spark=spark)
        return sink, spark

    def _run_pipeline_with_spark_sink(self, spark: MagicMock) -> object:
        import json
        import tempfile

        from document_intelligence.pipeline import ProcessingPipeline

        html = (
            "<html><head><title>Spark Delta Doc</title></head>"
            "<body><h1>Scope</h1><p>Content cites BGBl. Nr. 43/1975.</p></body></html>"
        )
        config = DeltaSinkConfig(
            published_documents_uri="gs://bucket/published_documents",
            published_sections_uri="gs://bucket/published_sections",
            processing_manifests_uri="gs://bucket/processing_manifests",
            published_commentary_insights_uri="gs://bucket/published_commentary_insights",
        )
        sink = SparkDeltaCanonicalSink(config, spark=spark)

        with tempfile.NamedTemporaryFile("w", suffix=".html", delete=False) as html_f:
            html_f.write(html)
            artifact_path = html_f.name
        with tempfile.NamedTemporaryFile("w", suffix=".json", delete=False) as manifest_f:
            json.dump(
                build_manifest_payload(artifact_path, artifact_role="primary_document"),
                manifest_f,
            )
            manifest_path = manifest_f.name

        try:
            pipeline = ProcessingPipeline(sink=sink, processing_version="di_test")
            return pipeline.process_event(build_bundle_event(manifest_path))
        finally:
            os.unlink(artifact_path)
            os.unlink(manifest_path)

    def test_persist_calls_spark_write_for_all_three_surfaces(self):
        spark = _make_mock_spark()
        self._run_pipeline_with_spark_sink(spark)

        # One write call per surface (3 total)
        self.assertEqual(spark.sparkContext.parallelize.call_count, 3)
        self.assertEqual(spark.read.json.call_count, 3)
        self.assertEqual(spark.read.json.return_value.write.format.call_count, 3)

    def test_persist_writes_in_append_mode(self):
        spark = _make_mock_spark()
        self._run_pipeline_with_spark_sink(spark)

        mock_write = spark.read.json.return_value.write
        for mode_call in mock_write.mode.call_args_list:
            self.assertEqual(mode_call, call("append"))

    def test_persist_sets_merge_schema_option(self):
        spark = _make_mock_spark()
        self._run_pipeline_with_spark_sink(spark)

        mock_write = spark.read.json.return_value.write
        for opt_call in mock_write.option.call_args_list:
            self.assertEqual(opt_call, call("mergeSchema", "true"))

    def test_persist_saves_to_correct_uris(self):
        spark = _make_mock_spark()
        self._run_pipeline_with_spark_sink(spark)

        saved_uris = [c.args[0] for c in spark.read.json.return_value.write.save.call_args_list]
        self.assertIn("gs://bucket/published_documents", saved_uris)
        self.assertIn("gs://bucket/published_sections", saved_uris)
        self.assertIn("gs://bucket/processing_manifests", saved_uris)

    def test_json_records_sent_to_parallelize_are_valid_json(self):
        spark = _make_mock_spark()
        self._run_pipeline_with_spark_sink(spark)

        for parallelize_call in spark.sparkContext.parallelize.call_args_list:
            records = parallelize_call.args[0]
            self.assertIsInstance(records, list)
            self.assertGreater(len(records), 0)
            for record_str in records:
                parsed = json.loads(record_str)
                self.assertIsInstance(parsed, dict)

    def test_status_and_processed_events_are_recorded(self):
        spark = _make_mock_spark()
        config = DeltaSinkConfig(
            published_documents_uri="gs://bucket/published_documents",
            published_sections_uri="gs://bucket/published_sections",
            processing_manifests_uri="gs://bucket/processing_manifests",
        )
        sink = SparkDeltaCanonicalSink(config, spark=spark)

        sink.record_status_events([{"a": 1}, {"b": 2}])
        sink.record_document_processed_event({"c": 3})

        self.assertEqual(sink.status_events, [{"a": 1}, {"b": 2}])
        self.assertEqual(sink.document_processed_events, [{"c": 3}])

    def test_persist_commentary_insights_calls_spark_write(self):
        spark = _make_mock_spark()
        config = DeltaSinkConfig(
            published_documents_uri="gs://bucket/published_documents",
            published_sections_uri="gs://bucket/published_sections",
            processing_manifests_uri="gs://bucket/processing_manifests",
            published_commentary_insights_uri="gs://bucket/published_commentary_insights",
        )
        sink = SparkDeltaCanonicalSink(config, spark=spark)

        sink.persist_commentary_insights([build_commentary_insight()])

        saved_uris = [c.args[0] for c in spark.read.json.return_value.write.save.call_args_list]
        self.assertIn("gs://bucket/published_commentary_insights", saved_uris)

    def test_missing_pyspark_raises_processing_error(self):
        config = DeltaSinkConfig(
            published_documents_uri="gs://bucket/docs",
            published_sections_uri="gs://bucket/sections",
            processing_manifests_uri="gs://bucket/manifests",
        )
        sink = SparkDeltaCanonicalSink(config)  # no explicit spark session

        with patch.dict("sys.modules", {"pyspark": None, "pyspark.sql": None}):
            with self.assertRaises(ProcessingError) as ctx:
                sink._get_spark()
        self.assertEqual(ctx.exception.code, "missing_pyspark_dependency")

    def test_delta_ready_rows_applied_before_spark_write(self):
        """Rows sent to spark.sparkContext.parallelize must have all expected surface columns."""
        spark = _make_mock_spark()
        self._run_pipeline_with_spark_sink(spark)

        # First parallelize call is for published_documents — check all required columns present
        first_call_records = spark.sparkContext.parallelize.call_args_list[0].args[0]
        doc_row = json.loads(first_call_records[0])
        for key in (
            "document_id",
            "document_revision",
            "processing_manifest_id",
            "title",
            "lifecycle_status",
            "extensions",
        ):
            self.assertIn(key, doc_row, f"Expected column '{key}' missing from published_documents row")
        self.assertGreater(len(doc_row["extensions"]["citations"]), 0)


if __name__ == "__main__":
    unittest.main()
