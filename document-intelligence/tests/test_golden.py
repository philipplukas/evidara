import hashlib
import json
import os
import shutil
import sys
import tempfile
import unittest

sys.path.insert(0, os.path.join(os.path.dirname(__file__), "..", "src"))
sys.path.insert(0, os.path.dirname(__file__))

from document_intelligence.ingest.loaders import BundleLoadError
from document_intelligence.pipeline import ProcessingPipeline
from support import fixture_path, load_json, replace_placeholders


class GoldenBundleTests(unittest.TestCase):
    def test_valid_golden_bundles(self) -> None:
        fixture_names = [
            "simple_html",
            "messy_html",
            "nested_headings",
            "no_heading_fallback",
            "html_div_fallback",
            "ris_xml",
            "ris_html_decision_vfgh",
            "ris_html_decision_vwgh",
            "ris_xml_decision_vfgh",
            "ris_xml_decision_vwgh",
            "ris_xml_law_consolidated",
            "ris_xml_law_short",
            "ch_commentary_html",
            "ch_fedlex_law_html",
            "ch_fedlex_bv_html",
        ]
        for fixture_name in fixture_names:
            with self.subTest(fixture=fixture_name):
                temp_dir, event_payload, expected = materialize_golden_fixture(fixture_name)
                try:
                    result = ProcessingPipeline(processing_version="di_2026_03_29").process_event(event_payload)

                    if "title" in expected:
                        self.assertEqual(result.document.title, expected["title"])
                    if "title_contains" in expected:
                        self.assertIn(expected["title_contains"], result.document.title or "")
                    if "section_count" in expected:
                        self.assertEqual(len(result.sections), expected["section_count"])
                    if "section_count_min" in expected:
                        self.assertGreaterEqual(len(result.sections), expected["section_count_min"])
                    self.assertEqual(
                        [event["payload"]["status"] for event in result.status_events],
                        expected["status_flow"],
                    )
                    if "key_headings" in expected:
                        headings = [section.title for section in result.sections if section.title]
                        for heading in expected["key_headings"]:
                            self.assertIn(heading, headings)
                    if "section_max_content_length" in expected:
                        longest = max((len(section.content) for section in result.sections), default=0)
                        self.assertLessEqual(
                            longest,
                            expected["section_max_content_length"],
                            "a single section swallowed the document body",
                        )
                    if "key_section_anchors" in expected:
                        anchors = {
                            section.title: section.metadata.get("anchor")
                            for section in result.sections
                            if section.title
                        }
                        for title, anchor in expected["key_section_anchors"].items():
                            self.assertEqual(anchors.get(title), anchor)
                    if "key_content_contains" in expected:
                        full_text = result.document.full_text or ""
                        for fragment in expected["key_content_contains"]:
                            self.assertIn(fragment, full_text, f"Missing content: {fragment}")
                    if "metadata_regeste_contains" in expected:
                        # #836: the headnote must survive the whole pipeline onto the
                        # canonical document, because `metadata.regeste` is what the
                        # search projection reads. Asserting only that the XML normalizer
                        # extracted it would have passed for months while the value never
                        # left the IR.
                        self.assertIn(
                            expected["metadata_regeste_contains"],
                            result.document.metadata.get("regeste") or "",
                        )
                    if "html_parse_used_fallback" in expected:
                        self.assertEqual(
                            result.document.metadata.get("html_parse_used_fallback"),
                            expected["html_parse_used_fallback"],
                        )
                finally:
                    shutil.rmtree(temp_dir)

    def test_invalid_bundle_without_primary_artifact(self) -> None:
        temp_dir, event_payload, expected = materialize_golden_fixture("invalid_no_primary")
        try:
            with self.assertRaises(BundleLoadError) as context:
                ProcessingPipeline(processing_version="di_2026_03_29").process_event(event_payload)
            self.assertEqual(context.exception.code, expected["error_code"])
        finally:
            shutil.rmtree(temp_dir)


def materialize_golden_fixture(fixture_name):
    fixture_root = fixture_path("golden", fixture_name)
    temp_dir = tempfile.mkdtemp()
    artifact_source = _discover_artifact_source(fixture_root)
    artifact_target = os.path.join(temp_dir, os.path.basename(artifact_source))
    shutil.copyfile(artifact_source, artifact_target)
    with open(artifact_target, "rb") as artifact_handle:
        artifact_payload = artifact_handle.read()

    manifest_template = load_json(os.path.join(fixture_root, "bundle-manifest.json"))
    manifest_data = replace_placeholders(
        manifest_template,
        {
            "__ARTIFACT_PATH__": artifact_target,
            "__ARTIFACT_SIZE__": str(len(artifact_payload)),
            "__ARTIFACT_CHECKSUM__": hashlib.sha256(artifact_payload).hexdigest(),
        },
    )
    manifest_path = os.path.join(temp_dir, "bundle-manifest.json")
    with open(manifest_path, "w", encoding="utf-8") as manifest_handle:
        json.dump(manifest_data, manifest_handle)

    with open(manifest_path, "rb") as manifest_reader:
        manifest_payload = manifest_reader.read()
    event_template = load_json(os.path.join(fixture_root, "event.json"))
    event_data = replace_placeholders(
        event_template,
        {
            "__MANIFEST_PATH__": manifest_path,
            "__MANIFEST_SIZE__": str(len(manifest_payload)),
            "__MANIFEST_CHECKSUM__": hashlib.sha256(manifest_payload).hexdigest(),
        },
    )
    expected = load_json(os.path.join(fixture_root, "expected.json"))
    return temp_dir, event_data, expected


def _discover_artifact_source(fixture_root: str) -> str:
    for candidate in ["document.html", "document.xml", "document.json"]:
        path = os.path.join(fixture_root, candidate)
        if os.path.exists(path):
            return path
    raise FileNotFoundError(f"no artifact file found in fixture {fixture_root}")


if __name__ == "__main__":
    unittest.main()
