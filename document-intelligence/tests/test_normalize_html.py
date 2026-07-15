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

    def test_article_container_keeps_nested_heading_and_paragraph_separate(self) -> None:
        """Fedlex wraps each provision in `<article id="art_N">`; the nested heading must survive."""
        html = (
            "<html><body><main>"
            '<article id="art_1"><h6><b>Art. 1</b> Zweck</h6>'
            '<div class="collapseable"><p>Erster Absatz.</p><p>Zweiter Absatz.</p></div></article>'
            '<article id="art_2"><h6><b>Art. 2</b> Geltung</h6><p>Dritter Absatz.</p></article>'
            "</main></body></html>"
        )
        ir = normalize_html_document(html, "art_fedlex")
        self.assertEqual(
            [(block.type, block.text) for block in ir.blocks],
            [
                ("heading", "Art. 1 Zweck"),
                ("paragraph", "Erster Absatz."),
                ("paragraph", "Zweiter Absatz."),
                ("heading", "Art. 2 Geltung"),
                ("paragraph", "Dritter Absatz."),
            ],
        )
        headings = [block for block in ir.blocks if block.type == "heading"]
        self.assertEqual([block.level for block in headings], [6, 6])
        self.assertEqual([block.attrs.get("anchor") for block in headings], ["art_1", "art_2"])
        # Body paragraphs inherit the enclosing article anchor.
        self.assertEqual(ir.blocks[1].attrs.get("anchor"), "art_1")

    def test_loose_text_in_container_becomes_paragraph_block(self) -> None:
        """Bare text directly inside a container still yields a block (no tag-strip fallback)."""
        html = "<html><head><title>T</title></head><body><article>Loser Text ohne p-Tag.</article></body></html>"
        ir = normalize_html_document(html, "art_loose")
        self.assertFalse(ir.metadata.get("html_parse_used_fallback"))
        self.assertEqual(len(ir.blocks), 1)
        self.assertEqual(ir.blocks[0].type, "paragraph")
        self.assertEqual(ir.blocks[0].text, "Loser Text ohne p-Tag.")

    def test_loose_text_flushed_before_sibling_block_starts(self) -> None:
        """Loose text is flushed when a child block opens, so it does not swallow the heading."""
        html = (
            "<html><body>"
            '<section id="sec_1">Vorspann.<h2>Kapitel 1</h2><p>Inhalt.</p>Nachspann.</section>'
            "</body></html>"
        )
        ir = normalize_html_document(html, "art_flush")
        self.assertEqual(
            [(block.type, block.text) for block in ir.blocks],
            [
                ("paragraph", "Vorspann."),
                ("heading", "Kapitel 1"),
                ("paragraph", "Inhalt."),
                ("paragraph", "Nachspann."),
            ],
        )
        self.assertEqual({block.attrs.get("anchor") for block in ir.blocks}, {"sec_1"})

    def test_unclosed_container_still_flushes_loose_text(self) -> None:
        html = "<html><body><main>Text ohne schliessendes Tag."
        ir = normalize_html_document(html, "art_unclosed")
        self.assertEqual([block.text for block in ir.blocks], ["Text ohne schliessendes Tag."])

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
