import os
import sys
import unittest

sys.path.insert(0, os.path.join(os.path.dirname(__file__), "..", "src"))
sys.path.insert(0, os.path.dirname(__file__))

from document_intelligence.contracts.envelope import EnvelopeError
from document_intelligence.ingest import resolve_artifact_bundle_event
from support import build_pubsub_push_envelope


class PubSubIngestTests(unittest.TestCase):
    def test_resolve_artifact_bundle_event_accepts_raw_event(self) -> None:
        event_payload = {
            "event_type": "artifact_bundle.available",
            "payload": {"bundle_manifest_id": "abm_123"},
        }

        self.assertEqual(resolve_artifact_bundle_event(event_payload), event_payload)

    def test_resolve_artifact_bundle_event_decodes_pubsub_push_envelope(self) -> None:
        event_payload = {
            "event_type": "artifact_bundle.available",
            "payload": {"bundle_manifest_id": "abm_123"},
        }

        self.assertEqual(
            resolve_artifact_bundle_event(build_pubsub_push_envelope(event_payload)),
            event_payload,
        )

    def test_resolve_artifact_bundle_event_rejects_invalid_pubsub_payload(self) -> None:
        with self.assertRaises(EnvelopeError) as raised:
            resolve_artifact_bundle_event({"message": {"data": "not-base64"}})

        self.assertIn("base64", str(raised.exception))
