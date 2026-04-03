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
    from document_intelligence.service.store import FilePublishedDocumentStore
except ImportError:
    TestClient = None  # type: ignore[misc, assignment]
    create_app = None  # type: ignore[misc, assignment]
    FilePublishedDocumentStore = None  # type: ignore[misc, assignment]

_DOC = "doc_01jq7bdptzqv3xs0c41xpw1ybg"
_PM = "pm_01jq7bhgy7g0pkj4f1d03f8f8c"


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

    def test_processing_manifest_query(self) -> None:
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
            del os.environ["DOCUMENT_SERVICE_BEARER_TOKEN"]


if __name__ == "__main__":
    unittest.main()
