import os
import sys
import unittest
from unittest import mock

sys.path.insert(0, os.path.join(os.path.dirname(__file__), "..", "src"))

from document_intelligence.normalize.html import normalize_html_document


class NormalizeHtmlDocumentTests(unittest.TestCase):
    def test_title_entity_decoded(self) -> None:
        html = (
            '<!DOCTYPE html><html lang="de-CH"><head>'
            '<meta charset="utf-8"/><title>Verordnung &#252;ber Muster</title></head>'
            "<body><p>Art. 1 Geltung.</p></body></html>"
        )
        ir = normalize_html_document(html, "art_test")
        self.assertEqual(ir.metadata.get("title"), "Verordnung über Muster")
        self.assertEqual(ir.metadata.get("language"), "de")
        self.assertFalse(ir.metadata.get("html_parse_used_fallback"))

    def test_div_only_body_uses_fallback_and_keeps_title_lang(self) -> None:
        html = (
            '<!DOCTYPE html><html lang="fr-CH"><head><title>Loi f&#233;d&#233;rale</title></head>'
            "<body>"
            '<iframe src="https://evil.example/track"></iframe>'
            "<div>Texte principal sans balise p. Art. 1 Application.</div>"
            "</body></html>"
        )
        ir = normalize_html_document(html, "art_div")
        self.assertTrue(ir.metadata.get("html_parse_used_fallback"))
        self.assertEqual(ir.metadata.get("title"), "Loi fédérale")
        self.assertEqual(ir.metadata.get("language"), "fr")
        self.assertEqual(len(ir.blocks), 1)
        self.assertIn("Art. 1 Application", ir.blocks[0].text)
        self.assertNotIn("evil.example", ir.blocks[0].text)
        self.assertTrue(ir.blocks[0].attrs.get("fallback"))

    def test_parser_feed_exception_falls_back(self) -> None:
        html = "<html><body><p>recover me</p></body></html>"
        with mock.patch(
            "document_intelligence.normalize.html.HTMLParser.feed",
            side_effect=ValueError("simulated parse failure"),
        ):
            ir = normalize_html_document(html, "art_exc")
        self.assertTrue(ir.metadata.get("html_parse_used_fallback"))
        self.assertEqual(ir.metadata.get("html_parse_recovery"), "exception")
        self.assertEqual(len(ir.blocks), 1)
        self.assertIn("recover me", ir.blocks[0].text)

    def test_main_wraps_div_extracts_without_fallback(self) -> None:
        """Semantic outer <main> keeps prose inside nested <div> without tag-strip fallback."""
        html = (
            '<!DOCTYPE html><html lang="de"><head><title>BGE 99 II 1</title></head>'
            "<body><main><div>Leitsatz: Haftung des Arbeitgebers. Art. 109 OR.</div></main></body></html>"
        )
        ir = normalize_html_document(html, "art_main_div")
        self.assertFalse(ir.metadata.get("html_parse_used_fallback"))
        self.assertEqual(ir.metadata.get("title"), "BGE 99 II 1")
        self.assertEqual(len(ir.blocks), 1)
        self.assertIn("Art. 109 OR", ir.blocks[0].text)
        self.assertNotIn("fallback", ir.blocks[0].attrs)

    def test_header_chrome_skipped_body_keeps_paragraph(self) -> None:
        html = (
            "<!DOCTYPE html><html><head><title>Test</title></head>"
            "<body>"
            "<header><nav>Site menu noise</nav></header>"
            "<p>Binding body paragraph.</p>"
            "</body></html>"
        )
        ir = normalize_html_document(html, "art_header")
        self.assertFalse(ir.metadata.get("html_parse_used_fallback"))
        self.assertEqual(len(ir.blocks), 1)
        self.assertEqual(ir.blocks[0].text, "Binding body paragraph.")
        self.assertNotIn("Site menu", ir.blocks[0].text)


if __name__ == "__main__":
    unittest.main()
