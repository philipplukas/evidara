"""Tests for legal citation extraction."""

from __future__ import annotations

from document_intelligence.nlp.citation_extractor import extract_citations


class TestSRCitations:
    def test_basic_sr(self):
        citations = extract_citations("Gemäss SR 210 ist das ZGB anwendbar.")
        sr = [c for c in citations if c.citation_type == "sr"]
        assert len(sr) == 1
        assert sr[0].text == "SR 210"
        assert sr[0].metadata["sr_number"] == "210"

    def test_sr_with_decimals(self):
        citations = extract_citations("SR 311.0 regelt das Strafrecht.")
        sr = [c for c in citations if c.citation_type == "sr"]
        assert len(sr) == 1
        assert sr[0].metadata["sr_number"] == "311.0"

    def test_multiple_sr(self):
        text = "Vgl. SR 210, SR 220 und SR 311.0."
        citations = extract_citations(text)
        sr = [c for c in citations if c.citation_type == "sr"]
        assert len(sr) == 3


class TestBGECitations:
    def test_basic_bge(self):
        citations = extract_citations("BGE 147 III 49 ist massgebend.")
        bge = [c for c in citations if c.citation_type == "bge"]
        assert len(bge) == 1
        assert "BGE 147 III 49" in bge[0].text

    def test_bge_with_erwaegung(self):
        citations = extract_citations("BGE 148 IV 234 E. 3.2 bestätigt dies.")
        bge = [c for c in citations if c.citation_type == "bge"]
        assert len(bge) == 1
        assert "E. 3.2" in bge[0].text


class TestEUCitations:
    def test_eu_regulation(self):
        citations = extract_citations("Regulation (EU) 2016/679 (DSGVO).")
        eu = [c for c in citations if c.citation_type == "eu_regulation"]
        assert len(eu) == 1
        assert "2016/679" in eu[0].text

    def test_eu_regulation_german(self):
        citations = extract_citations("Verordnung (EU) 2016/679 ist anwendbar.")
        eu = [c for c in citations if c.citation_type == "eu_regulation"]
        assert len(eu) == 1

    def test_eu_directive(self):
        citations = extract_citations("Directive 2013/36/EU gilt.")
        eu = [c for c in citations if c.citation_type == "eu_directive"]
        assert len(eu) == 1


class TestArticleCitations:
    def test_article_reference(self):
        citations = extract_citations("Art. 8 EMRK schützt das Privatleben.")
        art = [c for c in citations if c.citation_type == "article"]
        assert len(art) == 1
        assert "Art. 8 EMRK" in art[0].text

    def test_article_with_absatz(self):
        citations = extract_citations("Art. 261bis StGB verbietet Rassendiskriminierung.")
        art = [c for c in citations if c.citation_type == "article"]
        assert len(art) == 1
        assert "StGB" in art[0].text


class TestDeduplication:
    def test_deduplicates_same_citation(self):
        text = "SR 210 gilt. Gemäss SR 210 ist dies klar."
        citations = extract_citations(text)
        sr = [c for c in citations if c.citation_type == "sr"]
        assert len(sr) == 1

    def test_different_types_not_deduplicated(self):
        text = "SR 210 and BGE 147 III 49."
        citations = extract_citations(text)
        assert len(citations) == 2


class TestEdgeCases:
    def test_empty_text(self):
        assert extract_citations("") == []

    def test_no_citations(self):
        assert extract_citations("This is a normal sentence.") == []

    def test_mixed_citations(self):
        text = (
            "Die Bestimmungen von SR 220 (OR), insbesondere Art. 41 OR, "
            "sowie die Rechtsprechung in BGE 147 III 49, stehen im Einklang "
            "mit Regulation (EU) 2016/679."
        )
        citations = extract_citations(text)
        types = {c.citation_type for c in citations}
        assert "sr" in types
        assert "bge" in types
        assert "eu_regulation" in types
        assert "article" in types
