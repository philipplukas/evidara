"""Durable canonical sink round-trip: golden fixture -> lean read API (#523).

Proves that when canonical surface URIs are configured, ``ProcessingPipeline`` persists
through the Delta-backed ``DeltaCanonicalSink`` and the document-service reads the same
surfaces back, so ``GET /v1/documents/{id}/lean`` returns real title + sections + citations
instead of the degraded fallback (title ``Document {id}``, no sections/citations) produced
when nothing is durably stored.
"""

from __future__ import annotations

import os
import shutil
import sys
import tempfile
import unittest
from pathlib import Path

sys.path.insert(0, os.path.join(os.path.dirname(__file__), "..", "src"))
sys.path.insert(0, os.path.dirname(__file__))

try:
    import deltalake  # noqa: F401
    from starlette.testclient import TestClient

    from document_intelligence.persist.sinks import DeltaCanonicalSink, DeltaSinkConfig
    from document_intelligence.pipeline import ProcessingPipeline
    from document_intelligence.service.app import create_app
    from document_intelligence.service.store import DeltaPublishedDocumentStore

    _DEPS_AVAILABLE = True
except ImportError:
    _DEPS_AVAILABLE = False

from test_golden import materialize_golden_fixture

# Consolidated RIS law fixture: rich real title, many sections, and both document- and
# section-level citations, so the assertions distinguish real content from the thin fallback.
_FIXTURE = "ris_xml_law_consolidated"
_EXPECTED_TITLE_FRAGMENT = "Gleisdorfer Straße"


@unittest.skipUnless(_DEPS_AVAILABLE, "Install document-intelligence[service] + deltalake for round-trip test")
class LeanDurableRoundTripTests(unittest.TestCase):
    def test_lean_read_serves_real_content_after_durable_persist(self) -> None:
        fixture_dir, event_payload, _expected = materialize_golden_fixture(_FIXTURE)
        surfaces_dir = tempfile.mkdtemp()
        try:
            documents_uri = str(Path(surfaces_dir) / "published_documents")
            sections_uri = str(Path(surfaces_dir) / "published_sections")
            manifests_uri = str(Path(surfaces_dir) / "processing_manifests")

            # storage_options={} keeps the local tmpdir surfaces from picking up any DI_S3_* env.
            sink = DeltaCanonicalSink(
                DeltaSinkConfig(documents_uri, sections_uri, manifests_uri),
                storage_options={},
            )
            result = ProcessingPipeline(processing_version="di_2026_03_29", sink=sink).process_event(event_payload)
            document_id = result.document.document_id

            store = DeltaPublishedDocumentStore(documents_uri, sections_uri, storage_options={})
            client = TestClient(create_app(store))
            response = client.get(f"/v1/documents/{document_id}/lean")

            self.assertEqual(response.status_code, 200)
            body = response.json()

            # Real title, not the degraded "Document {id}" fallback.
            self.assertIn(_EXPECTED_TITLE_FRAGMENT, body.get("title") or "")
            self.assertNotEqual(body.get("title"), f"Document {document_id}")

            # Sections survive the durable round-trip.
            sections = body.get("sections") or []
            self.assertGreater(len(sections), 1)
            self.assertTrue(any((section.get("content") or "").strip() for section in sections))

            # Citations survive too, at both document (extensions) and section (metadata) level.
            document_citations = (body.get("extensions") or {}).get("citations") or []
            section_citations = [
                citation
                for section in sections
                for citation in ((section.get("metadata") or {}).get("citations") or [])
            ]
            self.assertTrue(
                document_citations or section_citations,
                "expected citations in the lean document but found none",
            )
            self.assertTrue(
                any(citation.get("citation_type") for citation in document_citations + section_citations),
                "expected typed citations in the lean document",
            )
        finally:
            shutil.rmtree(fixture_dir, ignore_errors=True)
            shutil.rmtree(surfaces_dir, ignore_errors=True)


if __name__ == "__main__":
    unittest.main()
