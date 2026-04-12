"""Tests for ResolvedField provenance tracking."""

from __future__ import annotations

import json
import os
import sys
import tempfile
import unittest

sys.path.insert(0, os.path.join(os.path.dirname(__file__), "..", "src"))
sys.path.insert(0, os.path.dirname(__file__))

from document_intelligence.extractors.metadata import (
    FieldProvenanceAudit,
    ResolvedField,
)
from document_intelligence.pipeline import ProcessingPipeline
from support import build_bundle_event, build_manifest_payload

SAMPLE_HTML = """
<html>
  <head><title>Sample Statute</title></head>
  <body>
    <h1>Section 1</h1><p>First section text.</p>
  </body>
</html>
"""


class TestResolvedField(unittest.TestCase):
    def test_to_dict(self):
        rf = ResolvedField(value="Test Title", source="structured", confidence=1.0)
        d = rf.to_dict()
        assert d == {"value": "Test Title", "source": "structured", "confidence": 1.0}


class TestFieldProvenanceAudit(unittest.TestCase):
    def test_set_records_field(self):
        audit = FieldProvenanceAudit()
        audit.set("title", "My Title", "structured", 1.0)
        assert audit.get_value("title") == "My Title"

    def test_first_tier_wins(self):
        audit = FieldProvenanceAudit()
        audit.set("title", "Structured Title", "structured")
        audit.set("title", "LLM Title", "llm", 0.9)
        assert audit.get_value("title") == "Structured Title"
        assert audit.fields["title"].source == "structured"

    def test_set_if_missing_does_not_overwrite(self):
        audit = FieldProvenanceAudit()
        audit.set("doc_type", "law", "structured")
        audit.set_if_missing("doc_type", "decision", "llm", 0.8)
        assert audit.get_value("doc_type") == "law"

    def test_none_values_are_skipped(self):
        audit = FieldProvenanceAudit()
        audit.set("title", None, "structured")
        assert audit.get_value("title") is None
        assert "title" not in audit.fields

    def test_to_dict_serializes_all_fields(self):
        audit = FieldProvenanceAudit()
        audit.set("title", "T", "structured")
        audit.set("court", "VfGH", "structured")
        d = audit.to_dict()
        assert "title" in d
        assert "court" in d
        assert d["title"]["source"] == "structured"


class TestProvenanceInPipeline(unittest.TestCase):
    def test_html_document_has_field_provenance_in_metadata(self):
        with tempfile.NamedTemporaryFile("w", suffix=".html", delete=False) as html_handle:
            html_handle.write(SAMPLE_HTML)
            artifact_path = html_handle.name

        with tempfile.NamedTemporaryFile("w", suffix=".json", delete=False) as manifest_handle:
            json.dump(build_manifest_payload(artifact_path, artifact_role="primary_document"), manifest_handle)
            manifest_path = manifest_handle.name

        try:
            result = ProcessingPipeline(
                processing_version="di_2026_04_11",
            ).process_event(build_bundle_event(manifest_path))

            fp = result.document.metadata.get("field_provenance")
            assert fp is not None, "field_provenance missing from metadata"
            assert "title" in fp
            assert fp["title"]["source"] == "structured"
            assert fp["title"]["value"] == "Sample Statute"
        finally:
            os.unlink(artifact_path)
            os.unlink(manifest_path)

    def test_ris_xml_document_has_source_family_provenance(self):
        from support import fixture_path

        xml_path = os.path.join(fixture_path("golden", "ris_xml_decision_vfgh"), "document.xml")
        with tempfile.NamedTemporaryFile("w", suffix=".xml", delete=False) as xml_handle:
            with open(xml_path, encoding="utf-8") as src:
                xml_handle.write(src.read())
            artifact_path = xml_handle.name

        manifest_data = build_manifest_payload(
            artifact_path,
            artifact_role="primary_document",
            content_type="application/xml",
        )
        with tempfile.NamedTemporaryFile("w", suffix=".json", delete=False) as manifest_handle:
            json.dump(manifest_data, manifest_handle)
            manifest_path = manifest_handle.name

        try:
            result = ProcessingPipeline(
                processing_version="di_2026_04_11",
            ).process_event(build_bundle_event(manifest_path))

            fp = result.document.metadata.get("field_provenance")
            assert fp is not None
            assert "source_family" in fp
            assert fp["source_family"]["source"] == "structured"
            assert fp["source_family"]["value"] == "decision"
        finally:
            os.unlink(artifact_path)
            os.unlink(manifest_path)


if __name__ == "__main__":
    unittest.main()
