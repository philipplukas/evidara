"""Tests for outbound document.processed event construction."""

from __future__ import annotations

import os
import sys
import unittest
from dataclasses import replace

sys.path.insert(0, os.path.join(os.path.dirname(__file__), "..", "src"))
sys.path.insert(0, os.path.dirname(__file__))

from document_intelligence.events.document_processed import build_document_processed_event
from test_adapters import build_processing_result


class BuildDocumentProcessedEventTests(unittest.TestCase):
    def test_empty_authority_id_becomes_null(self) -> None:
        result = build_processing_result()
        document = replace(result.document, authority_id="")
        event = build_document_processed_event(
            document=document,
            manifest=result.manifest,
            correlation_id="run_01jq7a3s9b7j4dndd9sgv6pb9d",
            causation_id="evt_01jq7bz6b7npge5hr2eb9n74ba",
        )
        self.assertIsNone(event["payload"]["authority_id"])


if __name__ == "__main__":
    unittest.main()
