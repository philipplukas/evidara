"""Unit tests for lean / plain-text helpers (no FastAPI dependency)."""

import unittest

try:
    import docling_core  # noqa: F401

    HAS_DOCLING_CORE = True
except ImportError:
    HAS_DOCLING_CORE = False

from document_intelligence.service.lean import (
    extract_plain_text,
    strip_layout_fields,
    to_lean_dict,
    to_plain_text,
)

_MINIMAL_DOCLING: dict = {
    "schema_name": "DoclingDocument",
    "version": "1.0.0",
    "name": "root",
    "furniture": {
        "self_ref": "#/root",
        "children": [],
        "content_layer": "body",
        "name": "_root_",
    },
}


class TestStripLayoutFields(unittest.TestCase):
    def test_removes_bbox_and_confidence(self) -> None:
        doc = {
            "name": "root",
            "bbox": [0, 0, 1, 1],
            "nested": {"confidence": 0.9, "text": "Hello"},
        }
        out = strip_layout_fields(doc)
        self.assertNotIn("bbox", out)
        self.assertNotIn("confidence", out["nested"])
        self.assertEqual(out["nested"]["text"], "Hello")

    def test_custom_bbox_suffix(self) -> None:
        doc = {"foo_custom_bbox": 1, "keep": 2}
        out = strip_layout_fields(doc)
        self.assertNotIn("foo_custom_bbox", out)
        self.assertEqual(out["keep"], 2)


class TestExtractPlainText(unittest.TestCase):
    def test_flattens_strings(self) -> None:
        doc = {"a": "Line one", "b": ["Line two", {"c": "Line three"}]}
        text = extract_plain_text(doc)
        self.assertIn("Line one", text)
        self.assertIn("Line two", text)
        self.assertIn("Line three", text)


@unittest.skipUnless(HAS_DOCLING_CORE, "docling-core not installed (install document-intelligence[service])")
class TestDoclingPreferredTransforms(unittest.TestCase):
    def test_to_lean_dict_uses_docling_export(self) -> None:
        out = to_lean_dict(_MINIMAL_DOCLING)
        self.assertEqual(out.get("schema_name"), "DoclingDocument")
        self.assertIn("furniture", out)

    def test_to_plain_text_minimal_doc(self) -> None:
        self.assertEqual(to_plain_text(_MINIMAL_DOCLING), "")


class TestLeanPlainTextFacade(unittest.TestCase):
    """``to_*`` fall back when payload is not a valid DoclingDocument."""

    def test_to_lean_dict_fallback_strips_bbox(self) -> None:
        raw = {"schema": "other", "bbox": [1, 2], "keep": True}
        out = to_lean_dict(raw)
        self.assertNotIn("bbox", out)
        self.assertTrue(out.get("keep"))

    def test_to_plain_text_fallback(self) -> None:
        raw = {"a": "hello"}
        self.assertIn("hello", to_plain_text(raw))


if __name__ == "__main__":
    unittest.main()
