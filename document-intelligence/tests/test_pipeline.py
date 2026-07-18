import json
import os
import sys
import tempfile
import unittest

sys.path.insert(0, os.path.join(os.path.dirname(__file__), "..", "src"))
sys.path.insert(0, os.path.dirname(__file__))

from document_intelligence.extractors.metadata import (
    MetadataExtractionCandidate,
)
from document_intelligence.ingest.docling_adapter import _is_placeholder_title as is_docling_placeholder_title
from document_intelligence.persist.sinks import InMemoryCanonicalSink
from document_intelligence.pipeline import ProcessingPipeline, _resolve_official_citation
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


class StubMetadataExtractor:
    def __init__(self, candidate: MetadataExtractionCandidate | None) -> None:
        self._candidate = candidate

    def extract(self, **kwargs) -> MetadataExtractionCandidate | None:
        return self._candidate


class ProcessingPipelineTests(unittest.TestCase):
    def test_docling_placeholder_title_guard_rejects_ris_placeholder(self) -> None:
        self.assertTrue(is_docling_placeholder_title("RIS Dokument"))
        self.assertTrue(is_docling_placeholder_title("RIS - Bundesrecht konsolidiert"))
        self.assertFalse(is_docling_placeholder_title("Bundesgesetz über digitale Register"))

    def test_official_citation_uses_publication_organ_from_ris_metadata(self) -> None:
        citation = _resolve_official_citation(
            {},
            {"publication_organ": "BGBl. I Nr. 12/2026"},
        )
        self.assertEqual(citation, "BGBl. I Nr. 12/2026")

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

    def test_processes_local_application_json_bundle_into_contract_valid_outputs(self) -> None:
        sample_json = '{"name": "left-pad", "version": "1.3.0", "description": "String left pad"}'
        with tempfile.NamedTemporaryFile("w", suffix=".json", delete=False, encoding="utf-8") as json_handle:
            json_handle.write(sample_json)
            artifact_path = json_handle.name

        with tempfile.NamedTemporaryFile("w", suffix=".json", delete=False) as manifest_handle:
            json.dump(
                build_manifest_payload(
                    artifact_path,
                    artifact_role="primary_document",
                    content_type="application/json",
                    parser_hints={
                        "expected_modalities": ["html"],
                        "expected_content_types": ["application/json"],
                        "preferred_primary_artifact_roles": ["primary_document"],
                        "ocr_expected": False,
                        "attachment_policy": "ignore",
                    },
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

            self.assertEqual(result.document.document_revision, 1)
            self.assertIn("left-pad", result.document.body_text or result.document.full_text)
            self.assertEqual(
                [event["payload"]["status"] for event in result.status_events],
                ["accepted", "processing", "canonical_ready"],
            )
            self.assertEqual(len(sink.document_processed_events), 1)
        finally:
            os.unlink(artifact_path)
            os.unlink(manifest_path)

    # ─── Document identity across acquisition runs (#652) ────────────────

    def _process_with(self, *, upstream_locator: str | None, artifact_id: str | None = None) -> str:
        """Process one bundle and return its document_id.

        Each call writes a *fresh* artifact file, mimicking a new acquisition run of
        the same law: the artifact id differs every time, exactly as it does in
        production where artifact ids are per-run ULIDs.
        """
        with tempfile.NamedTemporaryFile("w", suffix=".html", delete=False) as handle:
            handle.write(SAMPLE_HTML)
            artifact_path = handle.name

        payload = build_manifest_payload(artifact_path, artifact_role="primary_document")
        payload["upstream_locator"] = upstream_locator
        if artifact_id is not None:
            payload["artifacts"][0]["artifact_id"] = artifact_id

        with tempfile.NamedTemporaryFile("w", suffix=".json", delete=False) as handle:
            json.dump(payload, handle)
            manifest_path = handle.name

        try:
            result = ProcessingPipeline(sink=InMemoryCanonicalSink()).process_event(build_bundle_event(manifest_path))
            return result.document.document_id
        finally:
            os.unlink(artifact_path)
            os.unlink(manifest_path)

    def test_reacquiring_the_same_law_keeps_one_document_identity(self) -> None:
        # The #652 regression: two runs of the same source fetch the same ELI, so they
        # must be two revisions of ONE document — not two documents. Keying on the
        # per-run artifact id cloned the constitution on every run.
        eli = "https://fedlex.data.admin.ch/eli/cc/1999/404"
        first = self._process_with(upstream_locator=eli, artifact_id="art_01jq7ab8x4nm7m3qz3b8e9q2fk")
        second = self._process_with(upstream_locator=eli, artifact_id="art_01jq7ab8x4nm7m3qz3b8e9q2fm")

        self.assertEqual(first, second)

    def test_distinct_laws_keep_distinct_identities(self) -> None:
        # The failure mode the fix must not introduce: collapsing different documents.
        first = self._process_with(upstream_locator="https://fedlex.data.admin.ch/eli/cc/1999/404")
        second = self._process_with(upstream_locator="https://fedlex.data.admin.ch/eli/cc/2002/123")

        self.assertNotEqual(first, second)

    def test_without_a_locator_identity_falls_back_to_the_artifact(self) -> None:
        # Sources publishing no stable permalink keep the old behaviour rather than
        # collapsing onto a shared id.
        first = self._process_with(upstream_locator=None, artifact_id="art_01jq7ab8x4nm7m3qz3b8e9q2fn")
        second = self._process_with(upstream_locator=None, artifact_id="art_01jq7ab8x4nm7m3qz3b8e9q2fp")

        self.assertNotEqual(first, second)

    def test_blank_locator_is_treated_as_absent(self) -> None:
        first = self._process_with(upstream_locator="   ", artifact_id="art_01jq7ab8x4nm7m3qz3b8e9q2fn")
        second = self._process_with(upstream_locator="   ", artifact_id="art_01jq7ab8x4nm7m3qz3b8e9q2fp")

        self.assertNotEqual(first, second)

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
            self.assertIs(result.document.metadata.get("html_parse_used_fallback"), False)
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

    def test_processes_pdf_bundle_layout_aware_without_marginal_splice(self) -> None:
        # A PDF primary artifact must be read as bytes and normalised layout-aware, so a
        # marginal heading never splices into the body sentence (#590). This proves the
        # binary path end-to-end: read_artifact_bytes -> normalize_pdf_document -> sections.
        reportlab_canvas = __import__("reportlab.pdfgen.canvas", fromlist=["Canvas"])
        from reportlab.lib.pagesizes import A4

        _, page_height = A4
        pdf_buffer = tempfile.NamedTemporaryFile("wb", suffix=".pdf", delete=False)
        canvas = reportlab_canvas.Canvas(pdf_buffer, pagesize=A4)

        def _draw(x, y_top, text, font="Helvetica", size=11):
            canvas.setFont(font, size)
            canvas.drawString(x, page_height - y_top, text)

        _draw(200, 120, "Die Gemeinde ist zustaendig fuer")
        _draw(200, 138, "die Fuehrung des")
        _draw(45, 150, "Organisation", font="Helvetica-Bold", size=9)
        _draw(200, 156, "Hundeverzeichnisses und der Hundekontrolle.")
        canvas.showPage()
        canvas.save()
        pdf_buffer.close()
        artifact_path = pdf_buffer.name

        with tempfile.NamedTemporaryFile("w", suffix=".json", delete=False) as manifest_handle:
            json.dump(
                build_manifest_payload(
                    artifact_path,
                    artifact_role="primary_document",
                    content_type="application/pdf",
                    parser_hints={
                        "expected_modalities": ["pdf"],
                        "expected_content_types": ["application/pdf"],
                        "preferred_primary_artifact_roles": ["primary_document"],
                        "ocr_expected": False,
                        "attachment_policy": "ignore",
                    },
                ),
                manifest_handle,
            )
            manifest_path = manifest_handle.name

        try:
            result = ProcessingPipeline(processing_version="di_2026_07_15").process_event(
                build_bundle_event(manifest_path)
            )
            self.assertEqual(result.document.metadata["normalizer"], "pdf_v1")
            body = result.document.body_text or result.document.full_text
            self.assertIn("die Fuehrung des Hundeverzeichnisses", body)
            self.assertNotIn("des Organisation Hundeverzeichnisses", body)
            # No section's body text is corrupted by the marginal splice.
            for section in result.sections:
                self.assertNotIn("des Organisation Hundeverzeichnisses", section.content)
            validate_instance_against_contract(
                result.document.to_dict(),
                "schemas/document.schema.json",
            )
        finally:
            os.unlink(artifact_path)
            os.unlink(manifest_path)

    def test_high_confidence_llm_metadata_can_override_title_and_document_type(self) -> None:
        # Use HTML without a <title> tag so structured extraction leaves a gap,
        # triggering the LLM extractor via the cascade conditional check.
        html_no_title = """<html><body>
            <h1>Section 1</h1><p>First section text.</p>
            <h2>Section 2</h2><p>Second section text.</p>
        </body></html>"""
        with tempfile.NamedTemporaryFile("w", suffix=".html", delete=False) as html_handle:
            html_handle.write(html_no_title)
            artifact_path = html_handle.name

        manifest_data = build_manifest_payload(artifact_path, artifact_role="primary_document")
        manifest_data["source_defaults"].pop("document_type_hint", None)
        with tempfile.NamedTemporaryFile("w", suffix=".json", delete=False) as manifest_handle:
            json.dump(manifest_data, manifest_handle)
            manifest_path = manifest_handle.name

        try:
            result = ProcessingPipeline(
                processing_version="di_2026_04_09",
                enable_llm_extractor=True,
                llm_confidence_threshold=0.8,
                llm_metadata_extractor=StubMetadataExtractor(
                    MetadataExtractionCandidate(
                        title="LLM Selected Title",
                        document_type="commentary",
                        confidence=0.95,
                        model="test-model",
                        provider="stub",
                    )
                ),
            ).process_event(build_bundle_event(manifest_path))

            self.assertEqual(result.document.title, "LLM Selected Title")
            self.assertEqual(result.document.document_type, "commentary")
            self.assertTrue(result.document.metadata["llm_extraction"]["applied"])
            self.assertEqual(result.document.metadata["llm_extraction"]["model"], "test-model")
        finally:
            os.unlink(artifact_path)
            os.unlink(manifest_path)

    def test_llm_skipped_when_structured_extraction_sufficient(self) -> None:
        with tempfile.NamedTemporaryFile("w", suffix=".html", delete=False) as html_handle:
            html_handle.write(SAMPLE_HTML)
            artifact_path = html_handle.name

        with tempfile.NamedTemporaryFile("w", suffix=".json", delete=False) as manifest_handle:
            json.dump(build_manifest_payload(artifact_path, artifact_role="primary_document"), manifest_handle)
            manifest_path = manifest_handle.name

        try:
            result = ProcessingPipeline(
                processing_version="di_2026_04_09",
                enable_llm_extractor=True,
                llm_confidence_threshold=0.8,
                llm_metadata_extractor=StubMetadataExtractor(
                    MetadataExtractionCandidate(
                        title="Should Not Apply",
                        document_type="commentary",
                        confidence=0.95,
                        model="test-model",
                    )
                ),
            ).process_event(build_bundle_event(manifest_path))

            self.assertEqual(result.document.title, "Sample Statute")
            self.assertEqual(result.document.document_type, "law")
            llm_meta = result.document.metadata.get("llm_extraction", {})
            self.assertEqual(llm_meta.get("summary"), "skipped_structured_sufficient")
        finally:
            os.unlink(artifact_path)
            os.unlink(manifest_path)

    def test_low_confidence_llm_metadata_keeps_deterministic_document_fields(self) -> None:
        with tempfile.NamedTemporaryFile("w", suffix=".html", delete=False) as html_handle:
            html_handle.write(SAMPLE_HTML)
            artifact_path = html_handle.name

        with tempfile.NamedTemporaryFile("w", suffix=".json", delete=False) as manifest_handle:
            json.dump(build_manifest_payload(artifact_path, artifact_role="primary_document"), manifest_handle)
            manifest_path = manifest_handle.name

        try:
            result = ProcessingPipeline(
                processing_version="di_2026_04_09",
                enable_llm_extractor=True,
                llm_confidence_threshold=0.8,
                llm_metadata_extractor=StubMetadataExtractor(
                    MetadataExtractionCandidate(
                        title="Ignored LLM Title",
                        document_type="commentary",
                        confidence=0.4,
                        model="test-model",
                    )
                ),
            ).process_event(build_bundle_event(manifest_path))

            self.assertEqual(result.document.title, "Sample Statute")
            self.assertEqual(result.document.document_type, "law")
            self.assertFalse(result.document.metadata["llm_extraction"]["applied"])
            self.assertEqual(result.document.metadata["llm_extraction"]["confidence_threshold"], 0.8)
        finally:
            os.unlink(artifact_path)
            os.unlink(manifest_path)


if __name__ == "__main__":
    unittest.main()


class SectionCitationExtractionTests(unittest.TestCase):
    """Verify that per-section citation extraction is performed in _build_sections."""

    CITATION_HTML = """
    <html><head><title>Legal Document with Citations</title></head>
    <body>
      <h1>Overview</h1>
      <p>This section cites no specific law.</p>
      <h2>Legal Basis</h2>
      <p>Pursuant to SR 210 (ZGB) and Art. 8 EMRK, the following applies.</p>
      <h2>Case Law</h2>
      <p>BGE 147 III 49 is the leading authority here.</p>
    </body>
    </html>
    """

    def test_sections_without_citations_have_no_citations_key(self):
        with tempfile.NamedTemporaryFile("w", suffix=".html", delete=False) as html_handle:
            html_handle.write(self.CITATION_HTML)
            artifact_path = html_handle.name
        with tempfile.NamedTemporaryFile("w", suffix=".json", delete=False) as manifest_handle:
            json.dump(build_manifest_payload(artifact_path, artifact_role="primary_document"), manifest_handle)
            manifest_path = manifest_handle.name

        try:
            result = ProcessingPipeline(processing_version="di_test").process_event(build_bundle_event(manifest_path))
            overview_sections = [s for s in result.sections if s.title and "Overview" in s.title]
            self.assertEqual(len(overview_sections), 1)
            # The overview section has no citations
            self.assertNotIn("citations", overview_sections[0].metadata)
        finally:
            os.unlink(artifact_path)
            os.unlink(manifest_path)

    def test_sections_with_citations_have_citations_in_metadata(self):
        with tempfile.NamedTemporaryFile("w", suffix=".html", delete=False) as html_handle:
            html_handle.write(self.CITATION_HTML)
            artifact_path = html_handle.name
        with tempfile.NamedTemporaryFile("w", suffix=".json", delete=False) as manifest_handle:
            json.dump(build_manifest_payload(artifact_path, artifact_role="primary_document"), manifest_handle)
            manifest_path = manifest_handle.name

        try:
            result = ProcessingPipeline(processing_version="di_test").process_event(build_bundle_event(manifest_path))
            legal_basis_sections = [s for s in result.sections if s.title and "Legal Basis" in s.title]
            self.assertEqual(len(legal_basis_sections), 1)
            section = legal_basis_sections[0]
            self.assertIn("citations", section.metadata)
            citation_types = {c["citation_type"] for c in section.metadata["citations"]}
            self.assertIn("sr", citation_types)
            self.assertIn("article", citation_types)
        finally:
            os.unlink(artifact_path)
            os.unlink(manifest_path)

    def test_bge_citation_extracted_in_case_law_section(self):
        with tempfile.NamedTemporaryFile("w", suffix=".html", delete=False) as html_handle:
            html_handle.write(self.CITATION_HTML)
            artifact_path = html_handle.name
        with tempfile.NamedTemporaryFile("w", suffix=".json", delete=False) as manifest_handle:
            json.dump(build_manifest_payload(artifact_path, artifact_role="primary_document"), manifest_handle)
            manifest_path = manifest_handle.name

        try:
            result = ProcessingPipeline(processing_version="di_test").process_event(build_bundle_event(manifest_path))
            case_law_sections = [s for s in result.sections if s.title and "Case Law" in s.title]
            self.assertEqual(len(case_law_sections), 1)
            section = case_law_sections[0]
            self.assertIn("citations", section.metadata)
            bge_citations = [c for c in section.metadata["citations"] if c["citation_type"] == "bge"]
            self.assertEqual(len(bge_citations), 1)
            self.assertIn("BGE 147 III 49", bge_citations[0]["text"])
        finally:
            os.unlink(artifact_path)
            os.unlink(manifest_path)

    def test_citation_metadata_contains_required_fields(self):
        with tempfile.NamedTemporaryFile("w", suffix=".html", delete=False) as html_handle:
            html_handle.write(self.CITATION_HTML)
            artifact_path = html_handle.name
        with tempfile.NamedTemporaryFile("w", suffix=".json", delete=False) as manifest_handle:
            json.dump(build_manifest_payload(artifact_path, artifact_role="primary_document"), manifest_handle)
            manifest_path = manifest_handle.name

        try:
            result = ProcessingPipeline(processing_version="di_test").process_event(build_bundle_event(manifest_path))
            for section in result.sections:
                if "citations" in section.metadata:
                    for cit in section.metadata["citations"]:
                        self.assertIn("text", cit)
                        self.assertIn("citation_type", cit)
                        self.assertIn("start", cit)
                        self.assertIn("end", cit)
        finally:
            os.unlink(artifact_path)
            os.unlink(manifest_path)


class CommentaryInsightPipelineTests(unittest.TestCase):
    COMMENTARY_HTML = """
    <html><head><title>Kommentar zu Art. 754 OR</title></head>
    <body>
      <h1>Art. 754 OR</h1>
      <p>Art. 754 OR wird in der Lehre als Haftungsnorm fuer Organe erlaeutert.</p>
      <p>BGE 147 III 49 wird als Leitentscheid zur Verantwortlichkeit diskutiert.</p>
    </body>
    </html>
    """

    def test_commentary_insights_are_emitted_for_commentary_documents(self) -> None:
        with tempfile.NamedTemporaryFile("w", suffix=".html", delete=False) as html_handle:
            html_handle.write(self.COMMENTARY_HTML)
            artifact_path = html_handle.name

        manifest_data = build_manifest_payload(artifact_path, artifact_role="primary_document")
        manifest_data["source_defaults"]["document_type_hint"] = "commentary"
        manifest_data["source_defaults"]["authority_id"] = "auth_commentary_publisher"
        with tempfile.NamedTemporaryFile("w", suffix=".json", delete=False) as manifest_handle:
            json.dump(manifest_data, manifest_handle)
            manifest_path = manifest_handle.name

        try:
            result = ProcessingPipeline(
                processing_version="di_test",
                enable_commentary_insights=True,
            ).process_event(build_bundle_event(manifest_path))

            self.assertEqual(result.document.document_type, "commentary")
            self.assertGreaterEqual(len(result.commentary_insights), 2)
            for insight in result.commentary_insights:
                self.assertGreaterEqual(len(insight.support), 1)
                self.assertIn(insight.display_text, result.document.body_text)
            self.assertEqual(
                result.document.metadata["commentary_insights"]["emitted_count"],
                len(result.commentary_insights),
            )
        finally:
            os.unlink(artifact_path)
            os.unlink(manifest_path)

    def test_commentary_insights_are_not_emitted_for_law_documents(self) -> None:
        with tempfile.NamedTemporaryFile("w", suffix=".html", delete=False) as html_handle:
            html_handle.write(self.COMMENTARY_HTML)
            artifact_path = html_handle.name

        manifest_data = build_manifest_payload(artifact_path, artifact_role="primary_document")
        manifest_data["source_defaults"]["document_type_hint"] = "statute"
        with tempfile.NamedTemporaryFile("w", suffix=".json", delete=False) as manifest_handle:
            json.dump(manifest_data, manifest_handle)
            manifest_path = manifest_handle.name

        try:
            result = ProcessingPipeline(
                processing_version="di_test",
                enable_commentary_insights=True,
            ).process_event(build_bundle_event(manifest_path))

            self.assertEqual(result.document.document_type, "law")
            self.assertEqual(result.commentary_insights, [])
            self.assertEqual(result.document.metadata["commentary_insights"]["emitted_count"], 0)
        finally:
            os.unlink(artifact_path)
            os.unlink(manifest_path)
