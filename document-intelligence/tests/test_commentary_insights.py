import os
import sys
import unittest

sys.path.insert(0, os.path.join(os.path.dirname(__file__), "..", "src"))

from document_intelligence.canonical.models import Document, Section
from document_intelligence.contracts.envelope import Provenance
from document_intelligence.enrichment.commentary_insights import extract_commentary_insights
from document_intelligence.validate.validator import validate_commentary_insights


def _provenance() -> Provenance:
    return Provenance(
        tenant_id="tenant_public",
        corpus_id="corpus_public_ch_commentary",
        scope_type="global_public",
        source_id="src_01jq79xv3wdd6yr8q5bn0m3zfk",
        source_version_id="sv_01jq79zcskf4m3m4gm3t5s59xq",
        run_id="run_01jq7a3s9b7j4dndd9sgv6pb9d",
    )


def _document() -> Document:
    return Document(
        document_id="doc_01jq7bdptzqv3xs0c41xpw1ybg",
        document_revision=1,
        processing_manifest_id="pm_01jq7bhgy7g0pkj4f1d03f8f8c",
        provenance=_provenance(),
        primary_artifact_id="art_01jq7af3f8qqc46zc6xvkf9y4x",
        title="Kommentar zu Art. 754 OR",
        processed_at="2026-04-22T00:00:00Z",
        processing_version="di_test",
        lifecycle_status="active",
        full_text="Art. 754 OR wird in der Lehre erlaeutert.",
        body_text="Art. 754 OR wird in der Lehre erlaeutert.",
        jurisdiction_id="jur_ch_federal",
        authority_id="auth_commentary_publisher",
        document_type="commentary",
        metadata={"original_language": "de", "source_defaults": {"language_codes": ["de"]}},
    )


def _section(content: str) -> Section:
    return Section(
        section_id="sec_01jq7bprm7p1ef4rwr7s2j1bt3",
        document_id="doc_01jq7bdptzqv3xs0c41xpw1ybg",
        document_revision=1,
        processing_manifest_id="pm_01jq7bhgy7g0pkj4f1d03f8f8c",
        provenance=_provenance(),
        ordinal=0,
        depth=0,
        title="Art. 754 OR",
        content=content,
    )


class CommentaryInsightExtractorTests(unittest.TestCase):
    def test_extracts_citation_backed_passage_with_evidence_ref(self) -> None:
        passage = "Art. 754 OR wird in der Lehre als Haftungsnorm fuer Organe erlaeutert."

        insights = extract_commentary_insights(
            document=_document(),
            sections=[_section(passage)],
            min_confidence=0.7,
        )

        self.assertEqual(len(insights), 1)
        insight = insights[0]
        self.assertEqual(insight.insight_type, "referenced_provision")
        self.assertEqual(insight.display_text, passage)
        # `Art. 754 OR` now mints a canonical key (#594), so the passage is
        # backed by a RESOLVABLE authority rather than a bare string. The claim
        # carries the key, matching how every other keyed type already reads
        # ("References sr:210"); the human-readable form stays in
        # `display_text` and in the authority's own `text`.
        self.assertIn("abbrev_art:OR/754", insight.claim)
        self.assertEqual(insight.referenced_authorities[0]["text"], "Art. 754 OR")
        self.assertEqual(insight.referenced_authorities[0]["normalized_reference"], "abbrev_art:OR/754")
        self.assertEqual(insight.support[0]["ref_type"], "passage")
        self.assertEqual(insight.support[0]["passage"], passage)
        self.assertEqual(insight.language, "de")
        validate_commentary_insights(insights)

    def test_rejects_passages_without_citations(self) -> None:
        insights = extract_commentary_insights(
            document=_document(),
            sections=[_section("Dies ist eine allgemeine Erlaeuterung ohne Normzitat.")],
            min_confidence=0.7,
        )

        self.assertEqual(insights, [])

    def test_min_confidence_filters_fuzzy_references(self) -> None:
        """A citation that mints no key stays below the high-confidence bar.

        `Art. 754 OR` used to be the example here, but it is no longer fuzzy
        (#594): it resolves to `abbrev_art:OR/754`. A BGE reference is still
        genuinely unresolvable, so it is what now exercises the filter.
        """
        insights = extract_commentary_insights(
            document=_document(),
            sections=[_section("BGE 147 III 49 wird in der Lehre erlaeutert.")],
            min_confidence=0.9,
        )

        self.assertEqual(insights, [])

    def test_keyed_article_reference_clears_the_high_confidence_bar(self) -> None:
        """The flip side: a resolvable article reference is NOT filtered out."""
        insights = extract_commentary_insights(
            document=_document(),
            sections=[_section("Art. 754 OR wird in der Lehre erlaeutert.")],
            min_confidence=0.9,
        )

        self.assertEqual(len(insights), 1)


if __name__ == "__main__":
    unittest.main()
