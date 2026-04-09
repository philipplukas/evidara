import json
import os
import sys
import tempfile
import unittest

sys.path.insert(0, os.path.join(os.path.dirname(__file__), "..", "src"))
sys.path.insert(0, os.path.dirname(__file__))

from document_intelligence.persist.sinks import InMemoryCanonicalSink
from document_intelligence.pipeline import ProcessingPipeline
from document_intelligence.validate.schema_validation import (
    validate_instance_against_contract,
)
from support import build_bundle_event, build_manifest_payload

SAMPLE_HTML = """
<html>
  <head>
    <title>Sample Statute</title>
  </head>
  <body>
    <p>Introductory material before the first section.</p>
    <h1>Section 1</h1>
    <p>First section text.</p>
    <h2>Section 2</h2>
    <p>Second section text.</p>
  </body>
</html>
"""

SAMPLE_RIS_XML = """
<dokument xml:lang="de">
  <metadaten>
    <langtitel>Bundesgesetz über digitale Register</langtitel>
    <kurztitel>Digitalregistergesetz</kurztitel>
    <dokumentnummer>RIS-BUND-2026-0001</dokumentnummer>
    <gesetzesnummer>20012345</gesetzesnummer>
    <kundmachungsorgan>BGBl. I Nr. 12/2026</kundmachungsorgan>
  </metadaten>
  <text>
    <praeambel>Der Bund erlässt folgendes Bundesgesetz.</praeambel>
    <paragraf nummer="1">
      <ueberschrift>Geltungsbereich</ueberschrift>
      <absatz>(1) Dieses Bundesgesetz regelt digitale Register.</absatz>
    </paragraf>
    <paragraf nummer="2">
      <ueberschrift>Begriffsbestimmungen</ueberschrift>
      <ziffer nummer="1">Register ist eine strukturierte Datensammlung.</ziffer>
      <ziffer nummer="2">Behörde ist eine zuständige Bundesstelle.</ziffer>
    </paragraf>
  </text>
</dokument>
"""

SAMPLE_MARKDOWN = """
# Datenschutzgesetz

## Art. 1 Zweck
Dieses Gesetz schützt personenbezogene Daten.

## Art. 2 Geltungsbereich
- Es gilt für Bundesstellen.
- Es gilt für beauftragte Dritte.
"""


class ProcessingPipelineTests(unittest.TestCase):
    def test_processes_local_html_bundle_into_contract_valid_outputs(self) -> None:
        with tempfile.NamedTemporaryFile("w", suffix=".html", delete=False) as html_handle:
            html_handle.write(SAMPLE_HTML)
            artifact_path = html_handle.name

        with tempfile.NamedTemporaryFile("w", suffix=".json", delete=False) as manifest_handle:
            json.dump(
                build_manifest_payload(
                    artifact_path,
                    artifact_role="primary_document",
                ),
                manifest_handle,
            )
            manifest_path = manifest_handle.name

        try:
            sink = InMemoryCanonicalSink()
            pipeline = ProcessingPipeline(
                sink=sink,
                processing_version="di_2026_03_29",
            )
            result = pipeline.process_event(build_bundle_event(manifest_path))

            self.assertEqual(result.document.title, "Sample Statute")
            self.assertEqual(result.document.document_revision, 1)
            self.assertEqual(result.document.document_type, "law")
            self.assertEqual(result.document.jurisdiction_id, "jur_ch_federal")
            self.assertEqual(result.document.authority_id, "auth_fedlex")
            self.assertEqual(
                result.document.metadata["source_defaults"]["authority_name"],
                "Fedlex",
            )
            self.assertEqual(len(result.sections), 2)
            self.assertEqual(result.sections[0].title, "Section 1")
            self.assertIn("Introductory material", result.sections[0].content)
            self.assertEqual(result.sections[1].title, "Section 2")
            self.assertEqual(
                [event["payload"]["status"] for event in result.status_events],
                ["accepted", "processing", "canonical_ready"],
            )
            self.assertEqual(
                result.manifest.selected_profiles["jurisdiction_profile_ref"],
                "ch_jurisdiction_v1",
            )
            self.assertEqual(
                result.manifest.selected_profiles["resolution_policy_ref"],
                "official_primary_resolution_v1",
            )
            self.assertEqual(result.manifest.status, "canonical_ready")
            self.assertLess(result.sections[0].ordinal, result.sections[1].ordinal)
            self.assertEqual(result.sections[0].document_id, result.sections[1].document_id)
            self.assertEqual(
                result.sections[0].processing_manifest_id,
                result.sections[1].processing_manifest_id,
            )
            self.assertEqual(result.document.provenance.document_id, result.document.document_id)
            self.assertEqual(
                result.manifest.provenance.processing_manifest_id,
                result.manifest.processing_manifest_id,
            )
            self.assertEqual(len(sink.published_documents), 1)
            self.assertEqual(len(sink.published_sections), 2)
            self.assertEqual(len(sink.processing_manifests), 1)
            self.assertEqual(len(sink.status_events), 3)
            self.assertEqual(len(sink.document_processed_events), 1)
            self.assertEqual(
                result.document_processed_event["payload"]["authority_id"],
                "auth_fedlex",
            )
            self.assertEqual(
                result.document_processed_event["payload"]["authority_name"],
                "Fedlex",
            )
            self.assertTrue(result.document_processed_event["payload"]["is_official"])

            validate_instance_against_contract(
                result.document.to_dict(),
                "schemas/document.schema.json",
            )
            for section in result.sections:
                validate_instance_against_contract(
                    section.to_dict(),
                    "schemas/section.schema.json",
                )
            validate_instance_against_contract(
                result.manifest.to_dict(),
                "schemas/processing-manifest.schema.json",
            )
            for status_event in result.status_events:
                validate_instance_against_contract(
                    status_event,
                    "events/document-processing-status-updated.schema.json",
                )
            validate_instance_against_contract(
                result.document_processed_event,
                "events/document-processed.schema.json",
            )
        finally:
            os.unlink(artifact_path)
            os.unlink(manifest_path)

    def test_replay_keeps_document_identity_stable(self) -> None:
        with tempfile.NamedTemporaryFile("w", suffix=".html", delete=False) as html_handle:
            html_handle.write(SAMPLE_HTML)
            artifact_path = html_handle.name

        with tempfile.NamedTemporaryFile("w", suffix=".json", delete=False) as manifest_handle:
            json.dump(
                build_manifest_payload(
                    artifact_path,
                    artifact_role="primary_document",
                ),
                manifest_handle,
            )
            manifest_path = manifest_handle.name

        try:
            first = ProcessingPipeline(processing_version="di_2026_03_29").process_event(
                build_bundle_event(manifest_path)
            )
            second = ProcessingPipeline(processing_version="di_2026_03_29").process_event(
                build_bundle_event(manifest_path)
            )

            self.assertEqual(first.document.document_id, second.document.document_id)
            self.assertNotEqual(
                first.manifest.processing_manifest_id,
                second.manifest.processing_manifest_id,
            )
        finally:
            os.unlink(artifact_path)
            os.unlink(manifest_path)

    def test_processes_ris_style_xml_bundle(self) -> None:
        with tempfile.NamedTemporaryFile("w", suffix=".xml", delete=False) as xml_handle:
            xml_handle.write(SAMPLE_RIS_XML)
            artifact_path = xml_handle.name

        with tempfile.NamedTemporaryFile("w", suffix=".json", delete=False) as manifest_handle:
            json.dump(
                build_manifest_payload(
                    artifact_path,
                    artifact_role="primary_document",
                    content_type="application/xml",
                    parser_hints={
                        "expected_modalities": ["xml"],
                        "expected_content_types": ["application/xml"],
                        "preferred_primary_artifact_roles": ["primary_document"],
                        "ocr_expected": False,
                        "attachment_policy": "ignore",
                    },
                ),
                manifest_handle,
            )
            manifest_path = manifest_handle.name

        try:
            result = ProcessingPipeline(processing_version="di_2026_03_30").process_event(
                build_bundle_event(manifest_path)
            )

            self.assertEqual(result.document.title, "Bundesgesetz über digitale Register")
            self.assertEqual(result.document.document_type, "law")
            self.assertEqual(len(result.sections), 2)
            self.assertEqual(result.sections[0].title, "§ 1 Geltungsbereich")
            self.assertIn(
                "Der Bund erlässt folgendes Bundesgesetz.",
                result.sections[0].content,
            )
            self.assertEqual(result.sections[1].title, "§ 2 Begriffsbestimmungen")
            self.assertEqual(
                result.manifest.selected_profiles["source_profile_ref"],
                "default_xml_v1",
            )
            self.assertEqual(
                result.manifest.selected_profiles["jurisdiction_profile_ref"],
                "ch_jurisdiction_v1",
            )
            self.assertEqual(
                result.manifest.selected_profiles["normalization_profile_ref"],
                "xml_v1",
            )
            self.assertEqual(
                result.document.metadata["source_flavor"],
                "ris_like",
            )
            self.assertEqual(
                result.document.metadata["extracted_metadata"]["dokumentnummer"],
                "RIS-BUND-2026-0001",
            )
            self.assertEqual(
                result.document.metadata["extracted_metadata"]["gesetzesnummer"],
                "20012345",
            )
            self.assertEqual(
                result.document.metadata["official_citation"],
                "BGBl. I Nr. 12/2026",
            )
            self.assertEqual(result.document.metadata["original_language"], "de")
            self.assertEqual(result.document.metadata["translation_status"], "original")
            self.assertEqual(
                result.sections[0].metadata["official_label"],
                "§ 1",
            )

            validate_instance_against_contract(
                result.document.to_dict(),
                "schemas/document.schema.json",
            )
            for section in result.sections:
                validate_instance_against_contract(
                    section.to_dict(),
                    "schemas/section.schema.json",
                )
            validate_instance_against_contract(
                result.manifest.to_dict(),
                "schemas/processing-manifest.schema.json",
            )
        finally:
            os.unlink(artifact_path)
            os.unlink(manifest_path)

    def test_rejects_missing_manifest_path(self) -> None:
        pipeline = ProcessingPipeline()
        with self.assertRaises(Exception):
            pipeline.process_event(build_bundle_event("/tmp/does-not-exist.json"))

    def test_manifest_overrides_take_precedence_for_profile_refs(self) -> None:
        with tempfile.NamedTemporaryFile("w", suffix=".html", delete=False) as html_handle:
            html_handle.write(SAMPLE_HTML)
            artifact_path = html_handle.name

        with tempfile.NamedTemporaryFile("w", suffix=".json", delete=False) as manifest_handle:
            payload = build_manifest_payload(
                artifact_path,
                artifact_role="primary_document",
            )
            payload["di_overrides"] = {
                "source_profile_ref": "custom_source_v2",
                "jurisdiction_profile_ref": "custom_jurisdiction_v2",
                "resolution_policy_ref": "custom_resolution_v2",
                "normalization_profile_ref": "custom_norm_v2",
            }
            json.dump(payload, manifest_handle)
            manifest_path = manifest_handle.name

        try:
            result = ProcessingPipeline(processing_version="di_2026_04_05").process_event(
                build_bundle_event(manifest_path)
            )
            self.assertEqual(result.manifest.selected_profiles["source_profile_ref"], "custom_source_v2")
            self.assertEqual(
                result.manifest.selected_profiles["jurisdiction_profile_ref"],
                "custom_jurisdiction_v2",
            )
            self.assertEqual(
                result.manifest.selected_profiles["resolution_policy_ref"],
                "custom_resolution_v2",
            )
            self.assertEqual(
                result.manifest.selected_profiles["normalization_profile_ref"],
                "custom_norm_v2",
            )
        finally:
            os.unlink(artifact_path)
            os.unlink(manifest_path)

    def test_docling_backend_and_spacy_toggle_add_metadata_scaffolding(self) -> None:
        with tempfile.NamedTemporaryFile("w", suffix=".html", delete=False) as html_handle:
            html_handle.write(SAMPLE_HTML)
            artifact_path = html_handle.name

        with tempfile.NamedTemporaryFile("w", suffix=".json", delete=False) as manifest_handle:
            json.dump(
                build_manifest_payload(
                    artifact_path,
                    artifact_role="primary_document",
                ),
                manifest_handle,
            )
            manifest_path = manifest_handle.name

        try:
            result = ProcessingPipeline(
                processing_version="di_2026_04_03",
                parser_backend="docling",
                enable_spacy=True,
            ).process_event(build_bundle_event(manifest_path))
            self.assertEqual(
                result.manifest.selected_profiles["normalization_profile_ref"],
                "docling_fallback_v1",
            )
            self.assertIn("docling", result.document.metadata)
            self.assertIn("nlp", result.document.metadata)
            self.assertTrue(result.document.metadata["nlp"]["enabled"])
            self.assertEqual(result.document.metadata["docling"]["backend"], "fallback")
            self.assertEqual(result.document.metadata["nlp"]["model_name"], "xx_sent_ud_sm")
            self.assertEqual(result.document.metadata["nlp"]["max_chars_per_section"], 100000)
            self.assertEqual(result.document.metadata["nlp"]["batch_size"], 32)
        finally:
            os.unlink(artifact_path)
            os.unlink(manifest_path)

    def test_plain_text_content_type_with_html_payload_is_normalized_as_html(self) -> None:
        with tempfile.NamedTemporaryFile("w", suffix=".txt", delete=False) as text_handle:
            text_handle.write(SAMPLE_HTML)
            artifact_path = text_handle.name

        with tempfile.NamedTemporaryFile("w", suffix=".json", delete=False) as manifest_handle:
            json.dump(
                build_manifest_payload(
                    artifact_path,
                    artifact_role="primary_document",
                    content_type="text/plain",
                ),
                manifest_handle,
            )
            manifest_path = manifest_handle.name

        try:
            result = ProcessingPipeline(processing_version="di_2026_04_05").process_event(
                build_bundle_event(manifest_path)
            )
            self.assertEqual(result.document.title, "Sample Statute")
            self.assertEqual(result.document.metadata["normalizer"], "html_v1")
            self.assertEqual(result.document.metadata["source_flavor"], "structured_html")
        finally:
            os.unlink(artifact_path)
            os.unlink(manifest_path)

    def test_processes_markdown_source_family(self) -> None:
        with tempfile.NamedTemporaryFile("w", suffix=".md", delete=False) as markdown_handle:
            markdown_handle.write(SAMPLE_MARKDOWN)
            artifact_path = markdown_handle.name

        with tempfile.NamedTemporaryFile("w", suffix=".json", delete=False) as manifest_handle:
            json.dump(
                build_manifest_payload(
                    artifact_path,
                    artifact_role="primary_document",
                    content_type="text/markdown",
                ),
                manifest_handle,
            )
            manifest_path = manifest_handle.name

        try:
            result = ProcessingPipeline(processing_version="di_2026_04_05").process_event(
                build_bundle_event(manifest_path)
            )
            self.assertEqual(result.document.title, "Datenschutzgesetz")
            self.assertEqual(result.document.metadata["normalizer"], "markdown_v1")
            self.assertEqual(
                result.manifest.selected_profiles["source_profile_ref"],
                "default_markdown_v1",
            )
            self.assertEqual(len(result.sections), 2)
            self.assertEqual(result.sections[0].title, "Art. 1 Zweck")
            self.assertIn("personenbezogene Daten", result.sections[0].content)
            self.assertEqual(result.sections[1].title, "Art. 2 Geltungsbereich")
        finally:
            os.unlink(artifact_path)
            os.unlink(manifest_path)


if __name__ == "__main__":
    unittest.main()
