"""The pipeline actually emits a stage ledger, and it reaches the manifest.

`test_stage_ledger.py` tests the recorder in isolation. This tests the wiring —
that `process_event` opens a stage around each phase and that the result survives
into `ProcessingManifest.to_dict()`, which is what every downstream surface reads.
Without this, the recorder could be perfect and the pipeline could call none of it.
"""

import json
import os
import sys
import tempfile
import unittest

sys.path.insert(0, os.path.join(os.path.dirname(__file__), "..", "src"))
sys.path.insert(0, os.path.dirname(__file__))

from document_intelligence.observability.stage_ledger import STAGE_NAMES
from document_intelligence.persist.sinks import InMemoryCanonicalSink
from document_intelligence.pipeline import ProcessingPipeline
from document_intelligence.validate.schema_validation import (
    validate_instance_against_contract,
)
from support import build_bundle_event, build_manifest_payload
from test_pipeline import SAMPLE_HTML


class PipelineStageLedgerTests(unittest.TestCase):
    def _run(self):
        with tempfile.NamedTemporaryFile("w", suffix=".html", delete=False) as html_handle:
            html_handle.write(SAMPLE_HTML)
            artifact_path = html_handle.name

        with tempfile.NamedTemporaryFile("w", suffix=".json", delete=False) as manifest_handle:
            json.dump(
                build_manifest_payload(artifact_path, artifact_role="primary_document"),
                manifest_handle,
            )
            manifest_path = manifest_handle.name

        try:
            pipeline = ProcessingPipeline(
                sink=InMemoryCanonicalSink(),
                processing_version="di_stage_ledger_test",
            )
            return pipeline.process_event(build_bundle_event(manifest_path))
        finally:
            os.unlink(artifact_path)
            os.unlink(manifest_path)

    def test_every_declared_stage_is_recorded(self):
        """Delete any `with ledger.stage(...)` in `process_event` and this fails.

        The vocabulary is the contract: a stage that is declared but never opened
        would be absent from every manifest, which downstream reads as "that
        stage never ran" rather than "nobody instrumented it".
        """
        result = self._run()
        recorded = [stage["name"] for stage in result.manifest.stages]

        self.assertEqual(recorded, list(STAGE_NAMES))

    def test_stages_survive_into_the_serialised_manifest(self):
        """`to_dict()` is what every downstream surface reads."""
        payload = self._run().manifest.to_dict()

        self.assertIn("stages", payload)
        self.assertEqual(
            [stage["name"] for stage in payload["stages"]],
            list(STAGE_NAMES),
        )

    def test_each_stage_carries_a_duration(self):
        for stage in self._run().manifest.stages:
            with self.subTest(stage=stage["name"]):
                self.assertIn("duration_us", stage)
                self.assertIsInstance(stage["duration_us"], int)
                self.assertGreaterEqual(stage["duration_us"], 0)

    def test_sectionize_reports_the_sections_it_produced(self):
        """The counts are real measurements, not placeholders."""
        result = self._run()
        sectionize = next(s for s in result.manifest.stages if s["name"] == "sectionize")

        self.assertEqual(sectionize["items_in"], 1)
        self.assertEqual(sectionize["items_out"], len(result.sections))
        self.assertGreater(sectionize["items_out"], 0)

    def test_no_stage_reports_a_failure_on_a_clean_run(self):
        for stage in self._run().manifest.stages:
            with self.subTest(stage=stage["name"]):
                self.assertNotIn("failed", stage)
                self.assertNotIn("error_type", stage)

    def test_the_manifest_still_validates_against_its_contract(self):
        """`processing-manifest.schema.json` sets `additionalProperties: false`,
        so an undeclared `stages` key would fail here. This is what stops the
        producer and the contract drifting apart.
        """
        payload = self._run().manifest.to_dict()
        validate_instance_against_contract(payload, "schemas/processing-manifest.schema.json")

    def test_the_ledger_crosses_the_boundary_on_document_processed(self):
        """The control plane renders the timeline from this event, not from the
        lakehouse. Drop the `stages` block in `build_document_processed_event`
        and this fails — the manifest would still carry the ledger while every
        operator surface showed nothing.
        """
        result = self._run()
        payload = result.document_processed_event["payload"]

        self.assertIn("stages", payload)
        self.assertEqual(
            [stage["name"] for stage in payload["stages"]],
            [stage["name"] for stage in result.manifest.stages],
        )

    def test_the_emitted_event_validates_against_its_contract(self):
        """`payload` is `additionalProperties: false`, so an undeclared `stages`
        key fails here — this is what keeps the producer and the event contract
        from drifting.
        """
        validate_instance_against_contract(
            self._run().document_processed_event,
            "events/document-processed.schema.json",
        )


if __name__ == "__main__":
    unittest.main()
