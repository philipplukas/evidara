"""HTTP tests for Document Service (requires ``document-intelligence[service]``)."""

from __future__ import annotations

import json
import os
import tempfile
import unittest
from pathlib import Path

try:
    import deltalake
    import pyarrow as pa
    from starlette.testclient import TestClient

    from document_intelligence.service.app import create_app
    from document_intelligence.service.store import (
        DeltaPublishedDocumentStore,
        FilePublishedDocumentStore,
        store_from_env,
    )
except ImportError:
    deltalake = None  # type: ignore[misc, assignment]
    pa = None  # type: ignore[misc, assignment]
    TestClient = None  # type: ignore[misc, assignment]
    create_app = None  # type: ignore[misc, assignment]
    DeltaPublishedDocumentStore = None  # type: ignore[misc, assignment]
    FilePublishedDocumentStore = None  # type: ignore[misc, assignment]
    store_from_env = None  # type: ignore[misc, assignment]

_DOC = "doc_01jq7bdptzqv3xs0c41xpw1ybg"
_PM = "pm_01jq7bhgy7g0pkj4f1d03f8f8c"


def _write_published_documents(uri: str, rows: list[dict[str, object]]) -> None:
    assert pa is not None
    deltalake.write_deltalake(uri, pa.Table.from_pylist(rows))


@unittest.skipUnless(TestClient is not None, "Install document-intelligence[service] for HTTP tests")
class TestDocumentServiceHTTP(unittest.TestCase):
    def setUp(self) -> None:
        self._dir = tempfile.TemporaryDirectory()
        self.addCleanup(self._dir.cleanup)
        base = Path(self._dir.name)
        payload = {
            "schema": "docling-like",
            "bbox": [1, 2, 3],
            "body": {"text": "Hello"},
        }
        (base / f"{_DOC}.json").write_text(json.dumps(payload), encoding="utf-8")
        (base / f"{_DOC}__{_PM}.json").write_text(
            json.dumps({**payload, "rev": "specific"}),
            encoding="utf-8",
        )
        store = FilePublishedDocumentStore(base)
        self.app = create_app(store)
        self.client = TestClient(self.app)

    def test_full_returns_json(self) -> None:
        r = self.client.get(f"/v1/documents/{_DOC}")
        self.assertEqual(r.status_code, 200)
        self.assertEqual(r.json()["schema"], "docling-like")
        self.assertIn("bbox", r.json())

    def test_store_from_env_uses_content_dir(self) -> None:
        old_value = os.environ.get("DOCUMENT_SERVICE_CONTENT_DIR")
        os.environ["DOCUMENT_SERVICE_CONTENT_DIR"] = self._dir.name
        try:
            store = store_from_env()
            self.assertIsInstance(store, FilePublishedDocumentStore)
        finally:
            if old_value is None:
                os.environ.pop("DOCUMENT_SERVICE_CONTENT_DIR", None)
            else:
                os.environ["DOCUMENT_SERVICE_CONTENT_DIR"] = old_value

    def test_health_sets_correlation_headers(self) -> None:
        response = self.client.get("/health")
        self.assertEqual(response.status_code, 200)
        self.assertTrue(response.headers.get("X-Correlation-Id"))
        self.assertEqual(
            response.headers.get("X-Correlation-Id"),
            response.headers.get("X-Request-ID"),
        )

    def test_lean_strips_bbox(self) -> None:
        r = self.client.get(f"/v1/documents/{_DOC}/lean")
        self.assertEqual(r.status_code, 200)
        self.assertNotIn("bbox", r.json())

    def test_text_plain(self) -> None:
        r = self.client.get(f"/v1/documents/{_DOC}/text")
        self.assertEqual(r.status_code, 200)
        self.assertIn("text/plain", r.headers.get("content-type", ""))
        self.assertIn("Hello", r.text)

    def test_document_revision_query(self) -> None:
        r = self.client.get(f"/v1/documents/{_DOC}/lean?document_revision=1")
        self.assertEqual(r.status_code, 200)
        self.assertEqual(r.json()["schema"], "docling-like")

    def test_legacy_processing_manifest_query_still_works(self) -> None:
        r = self.client.get(f"/v1/documents/{_DOC}/lean?processing_manifest_id={_PM}")
        self.assertEqual(r.status_code, 200)
        self.assertEqual(r.json().get("rev"), "specific")

    def test_invalid_document_id(self) -> None:
        r = self.client.get("/v1/documents/not-a-doc/lean")
        self.assertEqual(r.status_code, 400)

    def test_invalid_pm_query(self) -> None:
        r = self.client.get(f"/v1/documents/{_DOC}/lean?processing_manifest_id=bad")
        self.assertEqual(r.status_code, 400)

    def test_not_found(self) -> None:
        missing = "doc_00000000000000000000000000"
        r = self.client.get(f"/v1/documents/{missing}/lean")
        self.assertEqual(r.status_code, 404)

    def test_bearer_required_when_configured(self) -> None:
        old_value = os.environ.get("DOCUMENT_SERVICE_BEARER_TOKEN")
        os.environ["DOCUMENT_SERVICE_BEARER_TOKEN"] = "secret-test-token"
        try:
            app = create_app(FilePublishedDocumentStore(Path(self._dir.name)))
            c = TestClient(app)
            r = c.get(f"/v1/documents/{_DOC}/lean")
            self.assertEqual(r.status_code, 401)
            r2 = c.get(
                f"/v1/documents/{_DOC}/lean",
                headers={"Authorization": "Bearer secret-test-token"},
            )
            self.assertEqual(r2.status_code, 200)
        finally:
            if old_value is None:
                os.environ.pop("DOCUMENT_SERVICE_BEARER_TOKEN", None)
            else:
                os.environ["DOCUMENT_SERVICE_BEARER_TOKEN"] = old_value


@unittest.skipUnless(deltalake is not None, "deltalake is not installed")
class TestDeltaPublishedDocumentStore(unittest.TestCase):
    def test_reads_latest_revision_by_default(self) -> None:
        with tempfile.TemporaryDirectory() as temp_dir:
            uri = str(Path(temp_dir) / "published_documents")
            _write_published_documents(
                uri,
                [
                    {
                        "document_id": _DOC,
                        "document_revision": 1,
                        "processing_manifest_id": _PM,
                        "provenance": {"run_id": "run_01jq7a3s9b7j4dndd9sgv6pb9d"},
                        "primary_artifact_id": "art_01jq7af3f8qqc46zc6xvkf9y4x",
                        "jurisdiction_id": "jur_ch_federal",
                        "authority_id": "auth_bvwg",
                        "title": "Older title",
                        "document_type": "decision",
                        "effective_date": "2024-01-01",
                        "processed_at": "2026-04-12T19:00:00Z",
                        "processing_version": "0.1.0-dev",
                        "lifecycle_status": "active",
                        "full_text": "older full",
                        "body_text": "older body",
                        "metadata": {"official_citation": "old"},
                        "extensions": {"source": "fixture-old"},
                    },
                    {
                        "document_id": _DOC,
                        "document_revision": 2,
                        "processing_manifest_id": "pm_01jq7chgy7g0pkj4f1d03f8f8c",
                        "provenance": {"run_id": "run_01jq7a3s9b7j4dndd9sgv6pb9d"},
                        "primary_artifact_id": "art_01jq7af3f8qqc46zc6xvkf9y4y",
                        "jurisdiction_id": "jur_ch_federal",
                        "authority_id": "auth_bvwg",
                        "title": "Newest title",
                        "document_type": "law",
                        "effective_date": "2024-02-01",
                        "processed_at": "2026-04-12T19:05:00Z",
                        "processing_version": "0.1.0-dev",
                        "lifecycle_status": "active",
                        "full_text": "new full",
                        "body_text": "new body",
                        "metadata": {"official_citation": "new"},
                        "extensions": {"source": "fixture-new"},
                    },
                ],
            )

            store = DeltaPublishedDocumentStore(uri)
            row = store.get_full(_DOC, None)

            self.assertIsNotNone(row)
            assert row is not None
            self.assertEqual(row["document_revision"], 2)
            self.assertEqual(row["title"], "Newest title")
            self.assertEqual(row["document_type"], "law")

    def test_reads_specific_document_revision(self) -> None:
        with tempfile.TemporaryDirectory() as temp_dir:
            uri = str(Path(temp_dir) / "published_documents")
            _write_published_documents(
                uri,
                [
                    {
                        "document_id": _DOC,
                        "document_revision": 1,
                        "processing_manifest_id": _PM,
                        "provenance": {"run_id": "run_01jq7a3s9b7j4dndd9sgv6pb9d"},
                        "primary_artifact_id": "art_01jq7af3f8qqc46zc6xvkf9y4x",
                        "jurisdiction_id": "jur_ch_federal",
                        "authority_id": "auth_bvwg",
                        "title": "Revision one",
                        "document_type": "decision",
                        "effective_date": "2024-01-01",
                        "processed_at": "2026-04-12T19:00:00Z",
                        "processing_version": "0.1.0-dev",
                        "lifecycle_status": "active",
                        "full_text": "older full",
                        "body_text": "older body",
                        "metadata": {"official_citation": "old"},
                        "extensions": {"source": "fixture-old"},
                    },
                    {
                        "document_id": _DOC,
                        "document_revision": 2,
                        "processing_manifest_id": "pm_01jq7chgy7g0pkj4f1d03f8f8c",
                        "provenance": {"run_id": "run_01jq7a3s9b7j4dndd9sgv6pb9d"},
                        "primary_artifact_id": "art_01jq7af3f8qqc46zc6xvkf9y4x",
                        "jurisdiction_id": "jur_ch_federal",
                        "authority_id": "auth_bvwg",
                        "title": "Revision two",
                        "document_type": "law",
                        "effective_date": "2024-02-01",
                        "processed_at": "2026-04-12T19:05:00Z",
                        "processing_version": "0.1.0-dev",
                        "lifecycle_status": "active",
                        "full_text": "new full",
                        "body_text": "new body",
                        "metadata": {"official_citation": "new"},
                        "extensions": {"source": "fixture-new"},
                    },
                ],
            )

            store = DeltaPublishedDocumentStore(uri)
            row = store.get_full(_DOC, 1)

            self.assertIsNotNone(row)
            assert row is not None
            self.assertEqual(row["document_revision"], 1)
            self.assertEqual(row["title"], "Revision one")


if __name__ == "__main__":
    unittest.main()
