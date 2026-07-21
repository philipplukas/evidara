"""Tests for legal citation extraction."""

from __future__ import annotations

from document_intelligence.nlp.citation_extractor import extract_citations, normalize_citation


class TestSwissLegislationCitations:
    """Swiss federal legislation (Fedlex) SR + article + statute forms.

    Mirrors the ``ch_fedlex_law_html`` golden fixture body so the citation
    forms that Stream E/G rely on stay covered at the extractor level.
    """

    _BODY = (
        "Bundesverfassung der Schweizerischen Eidgenossenschaft, SR 101. "
        "Sie foerdert die gemeinsame Wohlfahrt im Sinne von Art. 5 BV. "
        "Ergaenzend gilt das ZGB (SR 210)."
    )

    def test_sr_numbers_extracted(self):
        sr = {c.metadata["sr_number"] for c in extract_citations(self._BODY) if c.citation_type == "sr"}
        assert {"101", "210"} <= sr

    def test_article_reference_extracted(self):
        articles = [c for c in extract_citations(self._BODY) if c.citation_type == "article"]
        assert any("Art. 5 BV" in c.text for c in articles)


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


class TestAustrianCitations:
    def test_bgbl_number_year(self):
        citations = extract_citations("Die Kundmachung erfolgte in BGBl. Nr. 43/1975.")
        bgbl = [c for c in citations if c.citation_type == "at_bgbl"]
        assert len(bgbl) == 1
        assert bgbl[0].metadata["number"] == "43"
        assert bgbl[0].metadata["year"] == "1975"
        assert normalize_citation(bgbl[0]) == "at_bgbl:43/1975"

    def test_bgbl_part_number_year(self):
        citations = extract_citations("Vgl. BGBl. III Nr. 62/2013 zur Umsetzung.")
        bgbl = [c for c in citations if c.citation_type == "at_bgbl"]
        assert len(bgbl) == 1
        assert bgbl[0].metadata["part"] == "III"
        assert normalize_citation(bgbl[0]) == "at_bgbl:iii:62/2013"

    def test_bundesgesetzblatt_long_form(self):
        citations = extract_citations("Gemäß Bundesgesetzblatt Nr. 825 aus 1994 gilt die Fassung.")
        bgbl = [c for c in citations if c.citation_type == "at_bgbl"]
        assert len(bgbl) == 1
        assert bgbl[0].metadata["number"] == "825"
        assert bgbl[0].metadata["year"] == "1994"


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


class TestCelexCitations:
    def test_celex_regulation(self):
        citations = extract_citations("GDPR (CELEX 32016R0679) applies.")
        celex = [c for c in citations if c.citation_type == "eu_celex"]
        assert len(celex) == 1
        assert celex[0].metadata["celex"] == "32016R0679"
        assert celex[0].metadata["sector"] == "3"
        assert celex[0].metadata["year"] == "2016"
        assert celex[0].metadata["descriptor"] == "R"

    def test_celex_directive(self):
        citations = extract_citations("See 32019L0790 on copyright in the DSM.")
        celex = [c for c in citations if c.citation_type == "eu_celex"]
        assert len(celex) == 1
        assert celex[0].metadata["descriptor"] == "L"
        assert celex[0].metadata["year"] == "2019"

    def test_celex_non_legislation_sector(self):
        # Sector 6 = case law from earlier CELEX generations.
        citations = extract_citations("The decision 62019CJ0311 is relevant.")
        celex = [c for c in citations if c.citation_type == "eu_celex"]
        assert len(celex) == 1
        assert celex[0].metadata["sector"] == "6"


class TestEcliEuCitations:
    def test_ecli_court_of_justice(self):
        citations = extract_citations("Schrems II (ECLI:EU:C:2020:559) invalidated Privacy Shield.")
        ecli = [c for c in citations if c.citation_type == "eu_ecli"]
        assert len(ecli) == 1
        assert ecli[0].metadata["ecli"] == "ECLI:EU:C:2020:559"
        assert ecli[0].metadata["court"] == "court-of-justice"
        assert ecli[0].metadata["year"] == "2020"
        assert ecli[0].metadata["ordinal"] == "559"

    def test_ecli_general_court(self):
        citations = extract_citations("ECLI:EU:T:2020:338 settled the issue.")
        ecli = [c for c in citations if c.citation_type == "eu_ecli"]
        assert len(ecli) == 1
        assert ecli[0].metadata["court"] == "general-court"
        assert ecli[0].metadata["court_code"] == "T"

    def test_ecli_civil_service_tribunal(self):
        # Retired 2016 but historical citations still occur.
        citations = extract_citations("See ECLI:EU:F:2014:18 for background.")
        ecli = [c for c in citations if c.citation_type == "eu_ecli"]
        assert len(ecli) == 1
        assert ecli[0].metadata["court"] == "civil-service-tribunal"


class TestGermanCitations:
    def test_bverfge_volume_page(self):
        citations = extract_citations("Die Entscheidung BVerfGE 123, 45 ist einschlägig.")
        de = [c for c in citations if c.citation_type == "de_bverfge"]
        assert len(de) == 1
        assert "BVerfGE 123, 45" in de[0].text

    def test_bverfge_with_parenthetical_page(self):
        citations = extract_citations("Vgl. BVerfGE 123, 45 (67) zur Frage.")
        de = [c for c in citations if c.citation_type == "de_bverfge"]
        assert len(de) == 1
        assert "(67)" in de[0].text

    def test_bverfg_docket(self):
        citations = extract_citations("Die Sache 1 BvR 1234/56 betrifft das Grundrecht.")
        de = [c for c in citations if c.citation_type == "de_bverfg_docket"]
        assert len(de) == 1
        assert de[0].metadata["senate"] == "1"
        assert de[0].metadata["proceeding_type"] == "BvR"
        assert de[0].metadata["year"] == "56"

    def test_bghz_reporter(self):
        citations = extract_citations("Siehe BGHZ 145, 12 sowie die Folgeentscheidung.")
        de = [c for c in citations if c.citation_type == "de_bgh"]
        assert len(de) == 1
        assert de[0].metadata["reporter"] == "BGHZ"

    def test_bghst_reporter(self):
        citations = extract_citations("BGHSt 50, 100 ist grundlegend.")
        de = [c for c in citations if c.citation_type == "de_bgh"]
        assert len(de) == 1
        assert de[0].metadata["reporter"] == "BGHSt"

    def test_paragraph_with_bgb(self):
        citations = extract_citations("§ 823 BGB begründet die Haftung.")
        de = [c for c in citations if c.citation_type == "de_paragraph"]
        assert len(de) == 1
        assert de[0].metadata["statute"] == "BGB"

    def test_multi_paragraph_with_stgb(self):
        citations = extract_citations("§§ 242, 243 StGB regeln den Diebstahl.")
        de = [c for c in citations if c.citation_type == "de_paragraph"]
        assert len(de) == 1
        assert de[0].metadata["statute"] == "StGB"

    def test_de_ecli(self):
        citations = extract_citations("Siehe ECLI:DE:BVERFG:2020:rs20200120.1bvr164519 zur Frage.")
        de = [c for c in citations if c.citation_type == "de_ecli"]
        assert len(de) == 1
        assert de[0].metadata["court"] == "BVERFG"
        assert de[0].metadata["year"] == "2020"


class TestFrenchCitations:
    def test_code_civil_article(self):
        citations = extract_citations("Voir l'Art. 1240 du Code civil sur la responsabilité.")
        fr = [c for c in citations if c.citation_type == "fr_code_article"]
        assert len(fr) == 1
        assert "Code civil" in fr[0].text

    def test_code_penal_article_with_letter_prefix(self):
        citations = extract_citations("L'article L. 121-3 du Code pénal s'applique.")
        fr = [c for c in citations if c.citation_type == "fr_code_article"]
        assert len(fr) == 1
        assert "Code pénal" in fr[0].text

    def test_code_de_commerce(self):
        citations = extract_citations("Art. R. 611-1 du Code de commerce.")
        fr = [c for c in citations if c.citation_type == "fr_code_article"]
        assert len(fr) == 1

    def test_pourvoi_standalone(self):
        citations = extract_citations("Dans le pourvoi n° 18-12.345, la Cour...")
        fr = [c for c in citations if c.citation_type == "fr_pourvoi"]
        assert len(fr) == 1
        assert fr[0].metadata["number"] == "18-12.345"

    def test_cassation_civile_prefix(self):
        citations = extract_citations("Cass. civ. 1re, 12 mars 2020.")
        fr = [c for c in citations if c.citation_type == "fr_cassation"]
        assert len(fr) == 1

    def test_conseil_etat_docket(self):
        citations = extract_citations("CE, 21 mars 2021, n° 428318 a jugé...")
        fr = [c for c in citations if c.citation_type == "fr_conseil_etat"]
        assert len(fr) == 1
        assert fr[0].metadata["number"] == "428318"

    def test_fr_ecli(self):
        citations = extract_citations("ECLI:FR:CCASS:2021:CI00123 a tranché.")
        fr = [c for c in citations if c.citation_type == "fr_ecli"]
        assert len(fr) == 1
        assert fr[0].metadata["court"] == "CCASS"


class TestItalianCitations:
    def test_codice_civile_article(self):
        citations = extract_citations("Vedi art. 2043 c.c. sulla responsabilità.")
        it = [c for c in citations if c.citation_type == "it_codice_article"]
        assert len(it) == 1
        assert "c.c." in it[0].metadata["codice"].replace(" ", "")

    def test_codice_penale_article(self):
        citations = extract_citations("Art. 575 c.p. punisce l'omicidio.")
        it = [c for c in citations if c.citation_type == "it_codice_article"]
        assert len(it) == 1

    def test_articolo_long_form(self):
        citations = extract_citations("L'articolo 1321 c.c. definisce il contratto.")
        it = [c for c in citations if c.citation_type == "it_codice_article"]
        assert len(it) == 1

    def test_cassazione_civile(self):
        citations = extract_citations("Cass. civ. n. 1234/2020 ha stabilito che...")
        it = [c for c in citations if c.citation_type == "it_cassazione"]
        assert len(it) == 1
        assert it[0].metadata["number"] == "1234"
        assert it[0].metadata["year"] == "2020"

    def test_cassazione_penale_sezione(self):
        citations = extract_citations("Cass. pen., sez. III, n. 5678/2019 conferma.")
        it = [c for c in citations if c.citation_type == "it_cassazione"]
        assert len(it) == 1
        assert it[0].metadata["year"] == "2019"

    def test_consiglio_di_stato(self):
        citations = extract_citations("Cons. Stato, Sez. IV, n. 1234/2020 è rilevante.")
        it = [c for c in citations if c.citation_type == "it_consiglio_stato"]
        assert len(it) == 1
        assert it[0].metadata["number"] == "1234"

    def test_it_ecli(self):
        citations = extract_citations("La sentenza ECLI:IT:CASS:2020:1234CIV è decisiva.")
        it = [c for c in citations if c.citation_type == "it_ecli"]
        assert len(it) == 1
        assert it[0].metadata["court"] == "CASS"


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


class TestArticleCitationPrecision:
    """The precision gate on `article` citations (#594).

    `_ARTICLE_PATTERN`'s trailing token is positional, so before this gate the
    extractor read a statute's own article headings as citations to statutes
    named after the first word of the heading. On the real Bundesverfassung
    fixture that manufactured 187 phantom citations out of 188 matches, which
    padded the denominator of the citation graph's resolution rate until the
    metric measured mostly noise.
    """

    def test_real_bundesverfassung_yields_no_phantom_citations(self):
        """Regression against the FULL, REAL BV — the document that exposed it.

        The BV's headings ("Art. 36 Einschränkungen von Grundrechten") must
        contribute zero `article` citations. Asserting against the real
        fixture rather than a synthetic string is the point: the synthetic
        tests above passed throughout, because they only ever fed the shape
        the code already handled.
        """
        import re
        from pathlib import Path

        fixture = Path(__file__).parent / "golden" / "ch_fedlex_bv_html" / "document.html"
        text = re.sub(r"<[^>]+>", " ", fixture.read_text(encoding="utf-8", errors="ignore"))

        articles = [c for c in extract_citations(text) if c.citation_type == "article"]

        # Every surviving article citation names an abbreviation-shaped
        # statute. None is a German heading word.
        assert articles, "the BV genuinely cites other statutes; expected some to survive"
        for citation in articles:
            assert normalize_citation(citation) is not None, f"{citation.text!r} survived extraction but mints no key"

        # The specific phantoms this gate exists to kill.
        texts = " | ".join(c.text for c in articles)
        for heading_word in ("Einschränkungen", "Schweizerische", "Zweck", "Grundsätze"):
            assert heading_word not in texts

    def test_genuine_citation_survives(self):
        citations = extract_citations("Die Zuständigkeit richtet sich nach Art. 58 Abs. 1 ParlG.")
        articles = [c for c in citations if c.citation_type == "article"]
        assert len(articles) == 1
        assert articles[0].metadata["abbrev"] == "ParlG"
        assert articles[0].metadata["article"] == "58"
        assert articles[0].metadata["paragraph"] == "1"
        assert normalize_citation(articles[0]) == "abbrev_art:ParlG/58"

    def test_heading_is_not_a_citation(self):
        citations = extract_citations("Art. 36 Einschränkungen von Grundrechten")
        assert [c for c in citations if c.citation_type == "article"] == []


class TestSwissCantonalParagraphCitations:
    """Swiss cantonal and communal `§` references (#769).

    Cantonal and communal law spells its statutes out ("Hundegesetz") instead
    of abbreviating them, so `_DE_PARAGRAPH_PATTERN`'s curated list of GERMAN
    FEDERAL abbreviations matched nothing and the entire municipal rung
    extracted zero citations. The strings below are the ones actually observed
    in the Zürich ``Vollzugsvorschriften zum Hundegesetz`` acquired through the
    platform.
    """

    # Verbatim from the acquired ordinance: preamble, Art. 2-6.
    _ORDINANCE = (
        "gestützt auf § 2 Hundegesetz vom 14. April 2008 "
        "und § 17 Hundeverordnung vom 25. November 2009. "
        "Die Meldung erfolgt nach § 20 Hundeverordnung. "
        "Die Kosten richten sich nach § 24 Abs. 1 Hundegesetz. "
        "Vorbehalten bleibt § 24 Abs. 2 Hundegesetz. "
        "Es gelten § 17 Abs. 2 lit. a Hundeverordnung und "
        "§ 17 Abs. 2 lit. b Hundeverordnung. "
        "Der Vorsteher stützt sich auf § 2 Abs. 2 lit. d Hundegesetz sowie "
        "§ 2 Abs. 2 lit. e Hundegesetz."
    )

    def test_real_ordinance_references_are_extracted(self):
        """The nine references #769 reported as producing zero citations."""
        citations = extract_citations(self._ORDINANCE)
        texts = {c.text for c in citations if c.citation_type == "ch_paragraph"}

        assert texts == {
            "§ 2 Hundegesetz",
            "§ 17 Hundeverordnung",
            "§ 20 Hundeverordnung",
            "§ 24 Abs. 1 Hundegesetz",
            "§ 24 Abs. 2 Hundegesetz",
            "§ 17 Abs. 2 lit. a Hundeverordnung",
            "§ 17 Abs. 2 lit. b Hundeverordnung",
            "§ 2 Abs. 2 lit. d Hundegesetz",
            "§ 2 Abs. 2 lit. e Hundegesetz",
        }

    def test_subdivisions_are_recorded(self):
        citations = extract_citations("Der Vorsteher stützt sich auf § 2 Abs. 2 lit. d Hundegesetz.")
        ch = [c for c in citations if c.citation_type == "ch_paragraph"]
        assert len(ch) == 1
        assert ch[0].metadata == {
            "statute": "Hundegesetz",
            "paragraph": "2",
            "subsection": "2",
            "letter": "d",
        }

    def test_bare_paragraph_records_no_subdivisions(self):
        citations = extract_citations("Die Meldung erfolgt nach § 20 Hundeverordnung.")
        ch = [c for c in citations if c.citation_type == "ch_paragraph"]
        assert len(ch) == 1
        assert ch[0].metadata == {"statute": "Hundeverordnung", "paragraph": "20"}

    def test_stays_unresolved_rather_than_guessing(self):
        """A spelled-out cantonal title mints no key -- it is honestly unresolved.

        `citation-targets` keys short-title nodes off `title_short`, which a
        cantonal statute does not publish. The value of #769 is that the
        citation EXISTS and carries no target, so the ordinance presents as
        depending on a norm the corpus does not hold.
        """
        citations = extract_citations("Vorbehalten bleibt § 24 Abs. 1 Hundegesetz.")
        ch = [c for c in citations if c.citation_type == "ch_paragraph"]
        assert len(ch) == 1
        assert normalize_citation(ch[0]) is None


class TestSwissCantonalParagraphPrecision:
    """The suffix gate that keeps `§` from swallowing ordinary German prose."""

    def test_own_headings_are_not_citations(self):
        """A statute's own `§` headings have the same shape as a citation.

        This is the defect `_ARTICLE_PATTERN` was fixed for (187 phantoms out
        of 188 matches on the real BV). Heading words do not end in a legal
        instrument suffix, which is exactly what the gate tests.
        """
        headings = "§ 1 Zweck\n§ 2 Bewilligungspflicht\n§ 7 Hundehaltung\n§ 12 Geltungsbereich\n§ 15 Strafbestimmungen"
        assert [c for c in extract_citations(headings) if c.citation_type == "ch_paragraph"] == []

    def test_bare_prose_nouns_are_not_statutes(self):
        """ "Gesetz"/"Verordnung" alone name nothing addressable."""
        prose = "Dieses Gesetz tritt in Kraft nach § 5 Gesetz und § 6 Verordnung."
        assert [c for c in extract_citations(prose) if c.citation_type == "ch_paragraph"] == []

    def test_german_federal_paragraphs_are_untouched(self):
        """The curated German pattern must keep working and must not double-fire."""
        citations = extract_citations("§ 823 BGB begründet die Haftung; §§ 242, 243 StGB regeln den Diebstahl.")

        de = [c for c in citations if c.citation_type == "de_paragraph"]
        assert {c.metadata["statute"] for c in de} == {"BGB", "StGB"}
        assert [c for c in citations if c.citation_type == "ch_paragraph"] == []

    def test_spelled_out_german_statute_is_a_genuine_match(self):
        """German law spelled out is a real reference, not a false positive."""
        citations = extract_citations("Vgl. § 5 Bundesnaturschutzgesetz zur Landwirtschaft.")
        ch = [c for c in citations if c.citation_type == "ch_paragraph"]
        assert len(ch) == 1
        assert ch[0].metadata["statute"] == "Bundesnaturschutzgesetz"

    def test_real_bundesverfassung_yields_no_paragraph_citations(self):
        """The BV uses `Art.`, never `§` -- the new pattern must add nothing."""
        import re
        from pathlib import Path

        fixture = Path(__file__).parent / "golden" / "ch_fedlex_bv_html" / "document.html"
        text = re.sub(r"<[^>]+>", " ", fixture.read_text(encoding="utf-8", errors="ignore"))

        assert [c for c in extract_citations(text) if c.citation_type == "ch_paragraph"] == []
