"""Tests for normalize_citation function."""

from __future__ import annotations

import pytest

from document_intelligence.nlp.citation_extractor import Citation, normalize_citation


class TestNormalizeCitationDeterministic:
    def test_sr_normalization(self) -> None:
        c = Citation(text="SR 210", citation_type="sr", metadata={"sr_number": "210"})
        assert normalize_citation(c) == "sr:210"

    def test_celex(self) -> None:
        c = Citation(
            text="32016R0679",
            citation_type="eu_celex",
            metadata={"celex": "32016R0679"},
        )
        assert normalize_citation(c) == "celex:32016R0679"

    def test_ecli(self) -> None:
        c = Citation(
            text="ECLI:EU:C:2020:559",
            citation_type="eu_ecli",
            metadata={"ecli": "ECLI:EU:C:2020:559"},
        )
        assert normalize_citation(c) == "ecli:ECLI:EU:C:2020:559"

    def test_de_bverfg_docket(self) -> None:
        c = Citation(
            text="1 BvR 1234/56",
            citation_type="de_bverfg_docket",
            metadata={
                "senate": "1",
                "proceeding_type": "BvR",
                "ordinal": "1234",
                "year": "56",
            },
        )
        assert normalize_citation(c) == "de_docket:1 BvR 1234/56"

    def test_de_bverfg_docket_missing_field_returns_none(self) -> None:
        c = Citation(
            text="1 BvR 1234/56",
            citation_type="de_bverfg_docket",
            metadata={"senate": "1", "proceeding_type": "BvR"},
        )
        assert normalize_citation(c) is None


class TestNormalizeCitationSemiDeterministic:
    def test_eu_regulation_text_form(self) -> None:
        c = Citation(
            text="Regulation (EU) 2016/679",
            citation_type="eu_regulation",
        )
        assert normalize_citation(c) == "celex:32016R0679"

    def test_eu_directive_text_form(self) -> None:
        c = Citation(
            text="Directive 2013/36/EU",
            citation_type="eu_directive",
        )
        assert normalize_citation(c) == "celex:32013L0036"

    def test_de_paragraph_statute(self) -> None:
        c = Citation(
            text="§ 823 BGB",
            citation_type="de_paragraph",
            metadata={"statute": "BGB"},
        )
        assert normalize_citation(c) == "de_statute:BGB"

    def test_fr_pourvoi(self) -> None:
        c = Citation(
            text="n° 18-12.345",
            citation_type="fr_pourvoi",
            metadata={"number": "18-12.345"},
        )
        assert normalize_citation(c) == "fr_pourvoi:18-12.345"

    def test_fr_conseil_etat(self) -> None:
        c = Citation(
            text="CE, 12 mars 2020, n° 123456",
            citation_type="fr_conseil_etat",
            metadata={"number": "123456"},
        )
        assert normalize_citation(c) == "fr_ce:123456"

    def test_it_cassazione(self) -> None:
        c = Citation(
            text="Cass. civ. n. 1234/2020",
            citation_type="it_cassazione",
            metadata={"number": "1234", "year": "2020"},
        )
        assert normalize_citation(c) == "it_cass:1234/2020"

    def test_it_consiglio_stato(self) -> None:
        c = Citation(
            text="Cons. Stato n. 5678/2019",
            citation_type="it_consiglio_stato",
            metadata={"number": "5678", "year": "2019"},
        )
        assert normalize_citation(c) == "it_cds:5678/2019"

    def test_it_codice_article(self) -> None:
        c = Citation(
            text="art. 2043 c.c.",
            citation_type="it_codice_article",
            metadata={"codice": "Codice Civile"},
        )
        assert normalize_citation(c) == "it_codice:codicecivile"


class TestNormalizeCitationArticle:
    """`Art. 36 BV` -> `abbrev_art:BV/36` (#594).

    The key is minted from the short title the citation itself names. Whether
    a norm with that key EXISTS is a separate question, answered by
    `citation-targets` at resolution time.
    """

    def test_article_with_abbreviation(self) -> None:
        c = Citation(
            text="Art. 36 BV",
            citation_type="article",
            metadata={"article": "36", "abbrev": "BV"},
        )
        assert normalize_citation(c) == "abbrev_art:BV/36"

    def test_absatz_does_not_change_the_key(self) -> None:
        """Abs./lit. subdivide WITHIN an article; the article is the unit."""
        plain = Citation(
            text="Art. 36 BV",
            citation_type="article",
            metadata={"article": "36", "abbrev": "BV"},
        )
        with_absatz = Citation(
            text="Art. 36 Abs. 2 BV",
            citation_type="article",
            metadata={"article": "36", "abbrev": "BV", "paragraph": "2"},
        )
        assert normalize_citation(with_absatz) == normalize_citation(plain)

    def test_numbered_variant_is_a_distinct_provision(self) -> None:
        c = Citation(
            text="Art. 261bis StGB",
            citation_type="article",
            metadata={"article": "261bis", "abbrev": "StGB"},
        )
        assert normalize_citation(c) == "abbrev_art:StGB/261bis"

    def test_non_abbreviation_trailing_word_returns_none(self) -> None:
        """The BV's own headings must never mint a key.

        "Art. 36 Einschränkungen von Grundrechten" is a heading, not a
        citation to a statute called "Einschränkungen".
        """
        c = Citation(
            text="Art. 36 Einschränkungen",
            citation_type="article",
            metadata={"article": "36", "abbrev": "Einschränkungen"},
        )
        assert normalize_citation(c) is None


class TestNormalizeCitationFuzzy:
    @pytest.mark.parametrize(
        "citation_type",
        ["bge", "article", "fr_cassation"],
    )
    def test_fuzzy_returns_none(self, citation_type: str) -> None:
        c = Citation(text="some reference", citation_type=citation_type)
        assert normalize_citation(c) is None

    def test_bge_returns_none(self) -> None:
        """BGE references are deliberately still unresolved (#594)."""
        c = Citation(text="BGE 147 III 49", citation_type="bge")
        assert normalize_citation(c) is None
