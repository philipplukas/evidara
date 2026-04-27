"""Tests for bundle_metadata.extraction_hints (v1) and pipeline integration."""

from __future__ import annotations

import json
import os
import sys
import tempfile
import unittest

sys.path.insert(0, os.path.join(os.path.dirname(__file__), "..", "src"))
sys.path.insert(0, os.path.dirname(__file__))

from document_intelligence.contracts.envelope import ArtifactBundleManifest
from document_intelligence.extractors.extraction_hints import coerce_extraction_hints
from document_intelligence.pipeline import ProcessingPipeline
from support import build_bundle_event, build_manifest_payload


class TestCoerceExtractionHints(unittest.TestCase):
    def test_strips_unknown_keys(self):
        raw = {
            "title_hint": "  Real title  ",
            "future_field": "ignored",
            "docket_numbers": [" A1 ", "", "B2"],
        }
        out = coerce_extraction_hints(raw)
        assert out["title_hint"] == "Real title"
        assert out["docket_numbers"] == ["A1", "B2"]
        assert "future_field" not in out

    def test_non_dict_returns_empty(self):
        assert coerce_extraction_hints(None) == {}
        assert coerce_extraction_hints("x") == {}


class TestExtractionHintsInPipeline(unittest.TestCase):
    def test_placeholder_html_title_without_better_signal_becomes_untitled(self):
        html = """<html><head><title>RIS Dokument</title></head><body>
        <p>Body only.</p></body></html>"""
        with tempfile.NamedTemporaryFile("w", suffix=".html", delete=False) as f:
            f.write(html)
            artifact_path = f.name

        payload = build_manifest_payload(artifact_path, artifact_role="primary_document")
        with tempfile.NamedTemporaryFile("w", suffix=".json", delete=False) as mf:
            json.dump(payload, mf)
            manifest_path = mf.name

        try:
            result = ProcessingPipeline(processing_version="di_hints_test").process_event(
                build_bundle_event(manifest_path)
            )
            self.assertEqual(result.document.title, "Untitled document")
            fp = result.document.metadata.get("field_provenance", {})
            self.assertEqual(fp.get("title", {}).get("source"), "heuristic")
        finally:
            os.unlink(artifact_path)
            os.unlink(manifest_path)

    def test_title_hint_replaces_placeholder_html_title(self):
        html = """<html><head><title>RIS Dokument</title></head><body>
        <h1>Heading</h1><p>Body.</p></body></html>"""
        with tempfile.NamedTemporaryFile("w", suffix=".html", delete=False) as f:
            f.write(html)
            artifact_path = f.name

        payload = build_manifest_payload(artifact_path, artifact_role="primary_document")
        payload["bundle_metadata"] = {
            "extraction_hints": {
                "title_hint": "VfGH — G 1/2026 zu Beispiel",
                "document_type_hint": "decision",
            }
        }
        with tempfile.NamedTemporaryFile("w", suffix=".json", delete=False) as mf:
            json.dump(payload, mf)
            manifest_path = mf.name

        try:
            result = ProcessingPipeline(processing_version="di_hints_test").process_event(
                build_bundle_event(manifest_path)
            )
            self.assertEqual(result.document.title, "VfGH — G 1/2026 zu Beispiel")
            hint = result.document.metadata.get("extraction_hints", {}).get("title_hint")
            self.assertEqual(hint, "VfGH — G 1/2026 zu Beispiel")
            fp = result.document.metadata.get("field_provenance", {})
            self.assertEqual(fp.get("title", {}).get("source"), "manifest")
        finally:
            os.unlink(artifact_path)
            os.unlink(manifest_path)

    def test_title_hint_replaces_fedlex_shell_titles(self):
        for placeholder in ("Fedlex", "input-en", "input-de"):
            with self.subTest(placeholder=placeholder):
                html = f"""<html><head><title>{placeholder}</title></head><body>
                <p>Body.</p></body></html>"""
                with tempfile.NamedTemporaryFile("w", suffix=".html", delete=False) as f:
                    f.write(html)
                    artifact_path = f.name

                payload = build_manifest_payload(artifact_path, artifact_role="primary_document")
                payload["bundle_metadata"] = {
                    "extraction_hints": {
                        "title_hint": "Federal Act on Value Added Tax",
                        "document_type_hint": "legislation",
                    }
                }
                with tempfile.NamedTemporaryFile("w", suffix=".json", delete=False) as mf:
                    json.dump(payload, mf)
                    manifest_path = mf.name

                try:
                    result = ProcessingPipeline(processing_version="di_hints_test").process_event(
                        build_bundle_event(manifest_path)
                    )
                    self.assertEqual(result.document.title, "Federal Act on Value Added Tax")
                    fp = result.document.metadata.get("field_provenance", {})
                    self.assertEqual(fp.get("title", {}).get("source"), "manifest")
                finally:
                    os.unlink(artifact_path)
                    os.unlink(manifest_path)

    def test_placeholder_title_hint_does_not_win_over_structured_heading(self):
        html = """<html><head><title>RIS Dokument</title></head><body>
        <h1>VfGH — G 1/2026 zu Beispiel</h1><p>Body.</p></body></html>"""
        with tempfile.NamedTemporaryFile("w", suffix=".html", delete=False) as f:
            f.write(html)
            artifact_path = f.name

        payload = build_manifest_payload(artifact_path, artifact_role="primary_document")
        payload["bundle_metadata"] = {
            "extraction_hints": {
                "title_hint": "RIS Dokument",
                "document_type_hint": "decision",
            }
        }
        with tempfile.NamedTemporaryFile("w", suffix=".json", delete=False) as mf:
            json.dump(payload, mf)
            manifest_path = mf.name

        try:
            result = ProcessingPipeline(processing_version="di_hints_test").process_event(
                build_bundle_event(manifest_path)
            )
            self.assertEqual(result.document.title, "VfGH — G 1/2026 zu Beispiel")
            hint = result.document.metadata.get("extraction_hints", {}).get("title_hint")
            self.assertEqual(hint, "RIS Dokument")
            fp = result.document.metadata.get("field_provenance", {})
            self.assertEqual(fp.get("title", {}).get("source"), "structured")
        finally:
            os.unlink(artifact_path)
            os.unlink(manifest_path)

    def test_example_manifest_round_trip(self):
        root = os.path.join(os.path.dirname(__file__), "..", "..", "contracts", "examples")
        path = os.path.join(root, "artifact-bundle-manifest-extraction-hints.json")
        data = json.loads(open(path, encoding="utf-8").read())
        m = ArtifactBundleManifest.from_dict(data)
        hints = m.bundle_metadata.get("extraction_hints", {})
        coerced = coerce_extraction_hints(hints)
        self.assertIn("title_hint", coerced)
        self.assertIn("docket_numbers", coerced)
