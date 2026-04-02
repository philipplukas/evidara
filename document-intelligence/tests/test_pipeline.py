import json
import os
import sys
import tempfile
import unittest

sys.path.insert(0, os.path.join(os.path.dirname(__file__), "..", "src"))
sys.path.insert(0, os.path.dirname(__file__))

from document_intelligence.persist.sinks import InMemoryCanonicalSink
from document_intelligence.pipeline import ProcessingPipeline
from document_intelligence.validate.schema_validation import validate_instance_against_contract
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
            self.assertEqual(len(result.sections), 2)
            self.assertEqual(result.sections[0].title, "Section 1")
            self.assertIn("Introductory material", result.sections[0].content)
            self.assertEqual(result.sections[1].title, "Section 2")
            self.assertEqual(
                [event["payload"]["status"] for event in result.status_events],
                ["accepted", "processing", "canonical_ready"],
            )
            self.assertEqual(result.manifest.status, "canonical_ready")
            self.assertLess(result.sections[0].ordinal, result.sections[1].ordinal)
            self.assertEqual(
                result.sections[0].document_id, result.sections[1].document_id
            )
            self.assertEqual(
                result.sections[0].processing_manifest_id,
                result.sections[1].processing_manifest_id,
            )
            self.assertEqual(
                result.document.provenance.document_id, result.document.document_id
            )
            self.assertEqual(
                result.manifest.provenance.processing_manifest_id,
                result.manifest.processing_manifest_id,
            )
            self.assertEqual(len(sink.published_documents), 1)
            self.assertEqual(len(sink.published_sections), 2)
            self.assertEqual(len(sink.processing_manifests), 1)
            self.assertEqual(len(sink.status_events), 3)
            self.assertEqual(len(sink.document_processed_events), 1)

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

    def test_rejects_missing_manifest_path(self) -> None:
        pipeline = ProcessingPipeline()
        with self.assertRaises(Exception):
            pipeline.process_event(build_bundle_event("/tmp/does-not-exist.json"))


if __name__ == "__main__":
    unittest.main()
