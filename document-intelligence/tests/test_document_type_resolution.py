"""Unit tests for document type hint / extracted normalization."""

import os
import sys
import unittest

sys.path.insert(0, os.path.join(os.path.dirname(__file__), "..", "src"))

from document_intelligence.pipeline import _resolve_document_type


class ResolveDocumentTypeTests(unittest.TestCase):
    def test_hint_statute_maps_to_law(self) -> None:
        self.assertEqual(_resolve_document_type(None, "statute"), "law")

    def test_hint_judgment_maps_to_decision(self) -> None:
        self.assertEqual(_resolve_document_type(None, "judgment"), "decision")

    def test_extracted_urteil_maps_to_decision(self) -> None:
        self.assertEqual(_resolve_document_type("Urteil", None), "decision")

    def test_extracted_wins_before_hint(self) -> None:
        self.assertEqual(_resolve_document_type("law", "judgment"), "law")

    def test_invalid_extracted_falls_through_to_hint(self) -> None:
        self.assertEqual(_resolve_document_type("unknown_type", "statute"), "law")

    def test_both_unresolved_returns_none(self) -> None:
        self.assertIsNone(_resolve_document_type("nope", "still_no"))


if __name__ == "__main__":
    unittest.main()
