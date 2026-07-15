import os
import sys
import unittest

sys.path.insert(0, os.path.join(os.path.dirname(__file__), "..", "src"))

from document_intelligence.normalize.html import normalize_html_document
from document_intelligence.sectionize.html import build_sections_from_ir

# Shape of a Fedlex consolidated law: title > Titel > Kapitel > article, one <article> per provision.
_FEDLEX_HTML = (
    "<html><head><title>SR 101</title></head><body><main>"
    "<h1>Bundesverfassung</h1>"
    '<section id="lvl_2"><h2>2. Titel: Grundrechte</h2>'
    '<section id="lvl_2_1"><h3>1. Kapitel: Grundrechte</h3>'
    '<article id="art_35"><h6>Art. 35 Verwirklichung</h6><p>Die Grundrechte müssen wirken.</p></article>'
    '<article id="art_36"><h6>Art. 36 Einschränkungen</h6>'
    "<p>Einschränkungen bedürfen einer gesetzlichen Grundlage.</p>"
    "<p>Sie müssen verhältnismässig sein.</p></article>"
    "</section></section></main></body></html>"
)


class BuildSectionsFromIrTests(unittest.TestCase):
    def setUp(self) -> None:
        self.sections = build_sections_from_ir(normalize_html_document(_FEDLEX_HTML, "art_bv"))
        self.by_title = {section.title: section for section in self.sections}

    def test_each_article_becomes_its_own_section(self) -> None:
        titles = [section.title for section in self.sections]
        self.assertIn("Art. 35 Verwirklichung", titles)
        self.assertIn("Art. 36 Einschränkungen", titles)
        # Structural headings carry no direct text and are dropped; only real content survives.
        self.assertNotIn("2. Titel: Grundrechte", titles)

    def test_article_section_content_is_scoped_to_the_article(self) -> None:
        section = self.by_title["Art. 36 Einschränkungen"]
        self.assertIn("gesetzlichen Grundlage", section.content)
        self.assertIn("verhältnismässig", section.content)
        self.assertNotIn("Die Grundrechte müssen wirken", section.content)

    def test_article_section_carries_stable_anchor(self) -> None:
        self.assertEqual(self.by_title["Art. 36 Einschränkungen"].metadata["anchor"], "art_36")
        self.assertEqual(self.by_title["Art. 35 Verwirklichung"].metadata["anchor"], "art_35")

    def test_article_section_keeps_its_place_in_the_hierarchy(self) -> None:
        section = self.by_title["Art. 36 Einschränkungen"]
        self.assertEqual(section.depth, 5)
        self.assertEqual(section.metadata["heading_level"], 6)
        self.assertEqual(
            section.metadata["ancestor_titles"],
            ["Bundesverfassung", "2. Titel: Grundrechte", "1. Kapitel: Grundrechte"],
        )
        self.assertEqual(section.metadata["parent_title"], "1. Kapitel: Grundrechte")
        self.assertEqual(section.metadata["parent_anchor"], "lvl_2_1")

    def test_body_without_headings_falls_back_to_a_single_section(self) -> None:
        ir = normalize_html_document("<html><body><p>Nur Fliesstext.</p></body></html>", "art_flat")
        sections = build_sections_from_ir(ir)
        self.assertEqual(len(sections), 1)
        self.assertEqual(sections[0].section_type, "body")


if __name__ == "__main__":
    unittest.main()
