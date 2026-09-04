"""Tests for IcebergCanonicalSink + IcebergSinkConfig (ADR-0036).

The point of the Iceberg sink is that canonical surfaces become *named catalog
tables* instead of hardcoded storage URIs, so these tests pin the catalog
interaction (namespace/table creation, append) and the opt-in env contract —
not any particular storage layout.
"""

import dataclasses
import os
import sys
import unittest
from unittest.mock import MagicMock

import pyarrow as pa

sys.path.insert(0, os.path.join(os.path.dirname(__file__), "..", "src"))
sys.path.insert(0, os.path.dirname(__file__))

from document_intelligence.errors import ProcessingError
from document_intelligence.persist.sinks import (
    IcebergCanonicalSink,
    IcebergSinkConfig,
)
from test_adapters import build_commentary_insight, build_processing_result


def _make_catalog(*, table_exists: bool = False) -> MagicMock:
    catalog = MagicMock(name="Catalog")
    catalog.table_exists.return_value = table_exists
    catalog.create_table.return_value = MagicMock(name="CreatedTable")
    catalog.load_table.return_value = MagicMock(name="LoadedTable")
    return catalog


class _RecordingTable:
    """A catalog table that advertises the schema it was created with, and keeps appends."""

    def __init__(self, schema: pa.Schema, appended: list[pa.Table]) -> None:
        self._schema = schema
        self._appended = appended

    def schema(self) -> object:
        arrow_schema = self._schema

        class _IcebergSchema:
            def as_arrow(self) -> pa.Schema:
                return arrow_schema

        return _IcebergSchema()

    def append(self, table: pa.Table) -> None:
        self._appended.append(table)


class _RecordingCatalog:
    """A minimal catalog that behaves like a real one across two writes.

    The point is the *second* write: a table that already exists advertises the schema of
    the batch that created it, and the sink conforms the next batch to that schema. A
    `MagicMock` cannot say that — `_make_catalog` hands back `names=[]`, which sends every
    append down the inference path and never exercises the conformance step at all.
    """

    def __init__(self) -> None:
        self.tables: dict[str, _RecordingTable] = {}
        self.appended: dict[str, list[pa.Table]] = {}

    def create_namespace_if_not_exists(self, namespace: str) -> None:
        return None

    def table_exists(self, identifier: str) -> bool:
        return identifier in self.tables

    def load_table(self, identifier: str) -> _RecordingTable:
        return self.tables[identifier]

    def create_table(self, identifier: str, schema: pa.Schema) -> _RecordingTable:
        appended = self.appended.setdefault(identifier, [])
        table = _RecordingTable(schema, appended)
        self.tables[identifier] = table
        return table


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

    def test_a_new_metadata_key_survives_append_to_an_existing_table(self) -> None:
        """The Iceberg sink carries the same silent nested-field loss as Delta (#871).

        `_write_rows` conforms the batch to the table's committed schema with
        `pa.Table.from_pylist(rows, schema=...)`, and that applies the target type to
        *nested* fields as well — PyArrow drops a struct field the target struct does not
        declare, without raising. The comment at the call site promises the opposite for a
        new column ("the catalog rejects it loudly rather than silently"); that promise only
        ever held for top-level columns.

        `_RecordingCatalog` exists because `MagicMock` cannot state the one fact that
        matters: an existing table advertises the schema of the batch that *created* it.
        `_make_catalog`'s stand-in returns `names=[]`, so every append in the other tests
        falls straight through to inference and never meets the conformance step at all.

        No pyiceberg here, and none is needed: the field is gone before the catalog is
        reached, so the loss is provable at the Arrow layer where it happens.
        """
        catalog = _RecordingCatalog()
        sink = IcebergCanonicalSink(IcebergSinkConfig(namespace="evidara"), catalog=catalog)

        result = build_processing_result()
        without = dataclasses.replace(
            result.document,
            metadata={k: v for k, v in result.document.metadata.items() if k != "regeste"},
        )
        sink.persist(without, [], result.manifest)

        headnote = "Art. 754 OR; Verantwortlichkeit der Verwaltungsratsmitglieder."
        sink.persist(
            dataclasses.replace(without, metadata={**without.metadata, "regeste": headnote}),
            [],
            result.manifest,
        )

        appended = catalog.appended["evidara.published_documents"]
        self.assertEqual(len(appended), 2)
        self.assertNotIn("regeste", appended[0].to_pylist()[0]["metadata"])
        self.assertEqual(appended[1].to_pylist()[0]["metadata"]["regeste"], headnote)


if __name__ == "__main__":
    unittest.main()
