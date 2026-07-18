"""Tests for IcebergCanonicalSink + IcebergSinkConfig (ADR-0036).

The point of the Iceberg sink is that canonical surfaces become *named catalog
tables* instead of hardcoded storage URIs, so these tests pin the catalog
interaction (namespace/table creation, append) and the opt-in env contract —
not any particular storage layout.
"""

import os
import sys
import unittest
from unittest.mock import MagicMock

sys.path.insert(0, os.path.join(os.path.dirname(__file__), "..", "src"))
sys.path.insert(0, os.path.dirname(__file__))

from document_intelligence.errors import ProcessingError
from document_intelligence.persist.sinks import (
    IcebergCanonicalSink,
    IcebergSinkConfig,
)
from test_adapters import build_commentary_insight


def _make_catalog(*, table_exists: bool = False) -> MagicMock:
    catalog = MagicMock(name="Catalog")
    catalog.table_exists.return_value = table_exists
    catalog.create_table.return_value = MagicMock(name="CreatedTable")
    catalog.load_table.return_value = MagicMock(name="LoadedTable")
    return catalog


class IcebergSinkConfigTests(unittest.TestCase):
    def test_returns_none_without_a_configured_catalog(self) -> None:
        # Delta stays the default: no DI_ICEBERG_CATALOG_URI means no Iceberg.
        self.assertIsNone(IcebergSinkConfig.from_environment({}))
        self.assertIsNone(IcebergSinkConfig.from_environment({"DI_ICEBERG_CATALOG_URI": "  "}))

    def test_builds_rest_catalog_properties_and_reuses_di_s3_credentials(self) -> None:
        config = IcebergSinkConfig.from_environment(
            {
                "DI_ICEBERG_CATALOG_URI": "http://nessie:19120/iceberg/main",
                "DI_ICEBERG_WAREHOUSE": "warehouse",
                "DI_ICEBERG_NAMESPACE": "evidara",
                "DI_S3_ENDPOINT_URL": "http://minio:9000",
                "DI_S3_ACCESS_KEY_ID": "minioadmin",
                "DI_S3_SECRET_ACCESS_KEY": "minioadmin",
                "DI_S3_REGION": "us-east-1",
            }
        )
        assert config is not None
        self.assertEqual(config.namespace, "evidara")
        props = dict(config.catalog_properties)
        self.assertEqual(props["type"], "rest")
        self.assertEqual(props["uri"], "http://nessie:19120/iceberg/main")
        self.assertEqual(props["warehouse"], "warehouse")
        # Storage creds are shared with the bundle loader rather than duplicated.
        self.assertEqual(props["s3.endpoint"], "http://minio:9000")
        self.assertEqual(props["s3.access-key-id"], "minioadmin")
        self.assertEqual(props["s3.secret-access-key"], "minioadmin")
        # MinIO requires path-style addressing.
        self.assertEqual(props["s3.path-style-access"], "true")


class IcebergCanonicalSinkTests(unittest.TestCase):
    def _sink(self, catalog: MagicMock) -> IcebergCanonicalSink:
        return IcebergCanonicalSink(IcebergSinkConfig(namespace="evidara"), catalog=catalog)

    def test_creates_namespace_and_table_on_first_write(self) -> None:
        catalog = _make_catalog(table_exists=False)
        sink = self._sink(catalog)

        sink.persist_commentary_insights([build_commentary_insight()])

        catalog.create_namespace_if_not_exists.assert_called_once_with("evidara")
        # Addressed by NAME — the whole point of the catalog move.
        identifier = catalog.create_table.call_args.args[0]
        self.assertEqual(identifier, "evidara.published_commentary_insights")
        catalog.create_table.return_value.append.assert_called_once()

    def test_appends_to_existing_table_without_recreating_it(self) -> None:
        catalog = _make_catalog(table_exists=True)
        # Existing table advertises a schema the rows must conform to.
        existing = catalog.load_table.return_value
        existing.schema.return_value.as_arrow.return_value = MagicMock(names=[])
        sink = self._sink(catalog)

        sink.persist_commentary_insights([build_commentary_insight()])

        catalog.create_table.assert_not_called()
        catalog.load_table.assert_called_once_with("evidara.published_commentary_insights")
        existing.append.assert_called_once()

    def test_no_rows_is_a_no_op(self) -> None:
        catalog = _make_catalog()
        self._sink(catalog).persist_commentary_insights([])
        catalog.create_namespace_if_not_exists.assert_not_called()
        catalog.create_table.assert_not_called()

    def test_missing_commentary_table_raises_processing_error(self) -> None:
        catalog = _make_catalog()
        sink = IcebergCanonicalSink(
            IcebergSinkConfig(namespace="evidara", published_commentary_insights_table=None),
            catalog=catalog,
        )
        with self.assertRaises(ProcessingError) as ctx:
            sink.persist_commentary_insights([build_commentary_insight()])
        self.assertEqual(ctx.exception.code, "missing_commentary_insights_surface")

    def test_catalog_failure_surfaces_as_processing_error(self) -> None:
        catalog = _make_catalog(table_exists=False)
        catalog.create_table.side_effect = RuntimeError("catalog unavailable")
        sink = self._sink(catalog)
        with self.assertRaises(ProcessingError) as ctx:
            sink.persist_commentary_insights([build_commentary_insight()])
        self.assertEqual(ctx.exception.code, "iceberg_write_failed")

    def test_events_are_recorded_in_memory_like_the_delta_sink(self) -> None:
        sink = self._sink(_make_catalog())
        sink.record_status_events([{"a": 1}])
        sink.record_document_processed_event({"b": 2})
        self.assertEqual(sink.status_events, [{"a": 1}])
        self.assertEqual(sink.document_processed_events, [{"b": 2}])


if __name__ == "__main__":
    unittest.main()
