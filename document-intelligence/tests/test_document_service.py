"""HTTP tests for Document Service (requires ``document-intelligence[service]``)."""

from __future__ import annotations

import json
import os
import tempfile
import unittest
from pathlib import Path

try:
    from starlette.testclient import TestClient

    from document_intelligence.service.app import create_app
except ImportError:
    TestClient = None  # type: ignore[misc, assignment]
    create_app = None  # type: ignore[misc, assignment]

try:
    from document_intelligence.service.store import (
        FilePublishedDocumentStore,
        store_from_env,
    )
except ImportError:
    FilePublishedDocumentStore = None  # type: ignore[misc, assignment]
    store_from_env = None  # type: ignore[misc, assignment]

_DOC = "doc_01jq7bdptzqv3xs0c41xpw1ybg"
_PM = "pm_01jq7bhgy7g0pkj4f1d03f8f8c"


@unittest.skipUnless(
    TestClient is not None and create_app is not None,
    "Install document-intelligence[service] for HTTP tests",
)
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


class TestFilePublishedDocumentStore(unittest.TestCase):
    def test_reads_latest_revision_by_default(self) -> None:
        with tempfile.TemporaryDirectory() as temp_dir:
            base = Path(temp_dir)
            (base / f"{_DOC}__{_PM}.json").write_text(
                json.dumps(
                    {
                        "schema": "docling-like",
                        "bbox": [1, 2, 3],
                        "body": {"text": "older full"},
                        "official_citation": "old",
                    }
                ),
                encoding="utf-8",
            )
            (base / f"{_DOC}__pm_01jq7chgy7g0pkj4f1d03f8f8c.json").write_text(
                json.dumps(
                    {
                        "schema": "docling-like",
                        "bbox": [4, 5, 6],
                        "body": {"text": "new full"},
                        "official_citation": "new",
                    }
                ),
                encoding="utf-8",
            )

            store = FilePublishedDocumentStore(base)
            row = store.get_full(_DOC, None)

            self.assertIsNotNone(row)
            assert row is not None
            self.assertEqual(row["official_citation"], "new")

    def test_reads_specific_document_revision(self) -> None:
        with tempfile.TemporaryDirectory() as temp_dir:
            base = Path(temp_dir)
            (base / f"{_DOC}.json").write_text(
                json.dumps(
                    {
                        "schema": "docling-like",
                        "bbox": [1, 2, 3],
                        "body": {"text": "older full"},
                        "official_citation": "old",
                    }
                ),
                encoding="utf-8",
            )
            (base / f"{_DOC}__{_PM}.json").write_text(
                json.dumps(
                    {
                        "schema": "docling-like",
                        "bbox": [4, 5, 6],
                        "body": {"text": "new full"},
                        "official_citation": "new",
                    }
                ),
                encoding="utf-8",
            )

            store = FilePublishedDocumentStore(base)
            row = store.get_full(_DOC, _PM)

            self.assertIsNotNone(row)
            assert row is not None
            self.assertEqual(row["official_citation"], "new")


if __name__ == "__main__":
    unittest.main()
