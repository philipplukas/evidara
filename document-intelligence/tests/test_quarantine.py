"""ADR-0047: a manifestation whose text cannot support "this is law" never reaches canonical.

The tests that hold the line are the two end-to-end ones — an image-only PDF is withheld,
and the real ZH ordinance is not. The unit tests below them pin *why* each verdict was
reached, so a floor that stops working fails here rather than silently passing everything.

``reportlab`` and ``pdfplumber`` are imported hard, not via ``importorskip``, for the same
reason ``test_normalize_pdf.py`` gives: a module-level skip would delete the whole file
from the run and report green over the tests that exist to catch a fabricated corpus.
"""

from __future__ import annotations

import io
import json
import os
import re
import sys
import tempfile
import unittest
from pathlib import Path

from reportlab.lib.pagesizes import A4
from reportlab.pdfgen import canvas as reportlab_canvas

sys.path.insert(0, os.path.join(os.path.dirname(__file__), "..", "src"))
sys.path.insert(0, os.path.dirname(__file__))

from document_intelligence.normalize.ir import Block, NormalizedDocumentIR
from document_intelligence.normalize.pdf import normalize_pdf_document
from document_intelligence.normalize.quarantine import (
    DEFAULT_MIN_EXTRACTED_CHARS,
    DEFAULT_MIN_LEGAL_MARKERS,
    LEGAL_MARKER_PATTERN,
    QUARANTINE_REASONS,
    UPSTREAM_ASSESSED_CONTENT_TYPES,
    QuarantineThresholds,
    assess_quarantine,
    count_legal_markers,
)
from document_intelligence.persist.sinks import InMemoryCanonicalSink
from document_intelligence.pipeline import ProcessingPipeline
from document_intelligence.validate.validator import validate_processing_manifest
from support import build_bundle_event, build_manifest_payload

_REPO_ROOT = Path(__file__).resolve().parents[2]
_CONTENT_GATE = _REPO_ROOT / "platform-control" / "src" / "acquisition_core" / "content_gate.py"
_REAL_STATUTE_PDF = Path(__file__).resolve().parent / "fixtures" / "zh_as_554_510.pdf"
_MUNICIPAL_FIXTURE = Path(__file__).resolve().parent / "fixtures" / "bs_municipal_hundesteuer.json"

_PDF_PARSER_HINTS = {
    "expected_modalities": ["pdf"],
    "expected_content_types": ["application/pdf"],
    "preferred_primary_artifact_roles": ["primary_document"],
    "ocr_expected": False,
    "attachment_policy": "ignore",
}


def _image_only_pdf() -> bytes:
    """A structurally valid PDF with no text layer — a scan, or an image-only stub.

    This is the artifact every existing gate passes: it opens with ``%PDF-``, its declared
    content type matches, and at ~1 kB it is orders of magnitude above the 2 000-byte floor
    a *real* capture would face. ``normalize/pdf.py`` extracts nothing from it and — before
    this change — emitted an empty IR that satisfied every structural check downstream.
    """
    buffer = io.BytesIO()
    canvas = reportlab_canvas.Canvas(buffer, pagesize=A4)
    canvas.rect(100, 400, 300, 200, stroke=1, fill=1)
    canvas.circle(300, 300, 80, stroke=1, fill=0)
    canvas.showPage()
    canvas.save()
    return buffer.getvalue()


def _ir(text: str, *, metadata: dict | None = None) -> NormalizedDocumentIR:
    return NormalizedDocumentIR(
        blocks=[Block(id="blk_0000", type="paragraph", text=text, order=0, artifact_id="art_1")],
        metadata={"title": None, **(metadata or {})},
    )


class AssessQuarantineTests(unittest.TestCase):
    def test_no_text_layer_is_reported_before_the_content_floor(self) -> None:
        """An image-only PDF must name the *missing class*, not a threshold.

        Both reasons would be "true" of a zero-character PDF, and the difference decides
        what an operator does with the cohort: `no_text_layer` says "implement OCR",
        `below_content_floor` reads as "a number someone could lower". Ordering the checks
        is what keeps the queue a product backlog rather than a pile of tuning requests.
        """
        verdict = assess_quarantine(
            normalized_document=NormalizedDocumentIR(blocks=[], metadata={"pdf_no_text_layer": True}),
            content_type="application/pdf",
        )

        self.assertTrue(verdict.quarantined)
        self.assertEqual(verdict.reason, "no_text_layer")
        self.assertIn(verdict.reason, QUARANTINE_REASONS)

    def test_empty_output_without_a_pdf_flag_is_no_sections_extracted(self) -> None:
        verdict = assess_quarantine(
            normalized_document=NormalizedDocumentIR(blocks=[], metadata={}),
            content_type="application/pdf",
        )

        self.assertTrue(verdict.quarantined)
        self.assertEqual(verdict.reason, "no_sections_extracted")

    def test_character_floor_rejects_independently_of_the_marker_floor(self) -> None:
        """Marker-rich but far too short: a cover page that says "Art. 1" and stops."""
        text = "Art. 1 Abs. 1 Ziff. 2"
        self.assertGreaterEqual(count_legal_markers(text), DEFAULT_MIN_LEGAL_MARKERS)

        verdict = assess_quarantine(normalized_document=_ir(text), content_type="application/pdf")

        self.assertTrue(verdict.quarantined)
        self.assertEqual(verdict.reason, "below_content_floor")
        self.assertIn("characters of extracted text", verdict.detail or "")
        self.assertEqual(verdict.min_extracted_chars, DEFAULT_MIN_EXTRACTED_CHARS)

    def test_marker_floor_rejects_independently_of_the_character_floor(self) -> None:
        """Long enough, extracted cleanly, and not law: a consent interstitial."""
        text = (
            "Diese Website verwendet Cookies, um Ihnen die bestmoegliche Nutzung zu "
            "ermoeglichen. Bitte bestaetigen Sie Ihre Auswahl, bevor Sie fortfahren. "
            "Weitere Informationen finden Sie in unserer Datenschutzerklaerung sowie "
            "in den Nutzungsbedingungen dieses Portals."
        )
        self.assertGreater(len(text), DEFAULT_MIN_EXTRACTED_CHARS)
        self.assertEqual(count_legal_markers(text), 0)

        verdict = assess_quarantine(normalized_document=_ir(text), content_type="application/pdf")

        self.assertTrue(verdict.quarantined)
        self.assertEqual(verdict.reason, "below_content_floor")
        self.assertIn("legal-text marker", verdict.detail or "")
        self.assertEqual(verdict.legal_marker_count, 0)

    def test_text_modality_is_left_to_the_acquisition_gate(self) -> None:
        """`content_gate` already judged HTML at capture; re-judging it here is a second
        opinion on a settled question, not a gate on an unguarded one."""
        text = "Cookie notice. " * 20
        self.assertEqual(count_legal_markers(text), 0)

        verdict = assess_quarantine(normalized_document=_ir(text), content_type="text/html; charset=utf-8")

        self.assertFalse(verdict.quarantined)

    def test_per_source_overrides_narrow_the_floors(self) -> None:
        thresholds = QuarantineThresholds().with_overrides(
            {"quarantine_min_extracted_chars": 5000, "quarantine_min_legal_markers": 50}
        )
        self.assertEqual(thresholds.min_extracted_chars, 5000)
        self.assertEqual(thresholds.min_legal_markers, 50)

    def test_malformed_overrides_never_lower_a_floor(self) -> None:
        """A bad override must fail closed. Silently accepting `"none"` as zero would
        disable the gate from config, which is how a guard becomes decorative."""
        thresholds = QuarantineThresholds().with_overrides(
            {"quarantine_min_extracted_chars": "none", "quarantine_min_legal_markers": -1}
        )
        self.assertEqual(thresholds.min_extracted_chars, DEFAULT_MIN_EXTRACTED_CHARS)
        self.assertEqual(thresholds.min_legal_markers, DEFAULT_MIN_LEGAL_MARKERS)

    def test_an_explicit_zero_is_an_off_switch_and_not_a_rejected_override(self) -> None:
        """Distinct from the malformed case above, and worth pinning so nobody reads
        "malformed overrides fail closed" as "the floor cannot be switched off". It can."""
        thresholds = QuarantineThresholds().with_overrides(
            {"quarantine_min_extracted_chars": 0, "quarantine_min_legal_markers": 0}
        )
        self.assertEqual(thresholds.min_extracted_chars, 0)
        self.assertEqual(thresholds.min_legal_markers, 0)

        long_prose_without_law = "Cookie notice and nothing else at all. " * 20
        verdict = assess_quarantine(
            normalized_document=_ir(long_prose_without_law),
            content_type="application/pdf",
            thresholds=thresholds,
        )
        self.assertFalse(verdict.quarantined)


class MarkerVocabularyDriftTests(unittest.TestCase):
    """ADR-0047: the two gates "must not drift into separate opinions about what law
    looks like". They live in separate distributions, so this reads the upstream source."""

    def _content_gate_source(self) -> str:
        if not _CONTENT_GATE.exists():
            self.skipTest(f"platform-control not checked out beside document-intelligence: {_CONTENT_GATE}")
        return _CONTENT_GATE.read_text(encoding="utf-8")

    def test_every_upstream_marker_is_also_a_di_marker(self) -> None:
        source = self._content_gate_source()
        match = re.search(r"_LEGAL_MARKER_RE = re\.compile\(\s*r\"([^\"]+)\"", source)
        self.assertIsNotNone(match, "could not locate _LEGAL_MARKER_RE in content_gate.py")
        upstream_alternatives = match.group(1).split("|")

        di_alternatives = set(LEGAL_MARKER_PATTERN.split("|"))
        missing = [alt for alt in upstream_alternatives if alt not in di_alternatives]
        self.assertEqual(
            missing,
            [],
            "acquisition counts legal-text markers this gate does not: a document acquisition "
            f"accepted as law would be quarantined here for lacking them — {missing}",
        )

    def test_this_gate_is_never_stricter_than_acquisition(self) -> None:
        """The thresholds legitimately differ — the relation is what must hold.

        `content_gate` judges a whole HTML portal page; this gate judges the extracted text
        of one PDF manifestation, and the shortest real law in the repo carries two markers
        (see `MunicipalLawHeadroomTests`). What must never happen is a DI floor *above*
        acquisition's: acquisition would accept a document as law and DI would then withhold
        it, which is a contradiction the corpus cannot express.
        """
        source = self._content_gate_source()
        match = re.search(r"DEFAULT_MIN_LEGAL_MARKERS = (\d+)", source)
        self.assertIsNotNone(match)
        self.assertLessEqual(
            DEFAULT_MIN_LEGAL_MARKERS,
            int(match.group(1)),
            "DI's marker floor is stricter than acquisition's, so a capture accepted as law "
            "upstream would be quarantined here",
        )

    def test_di_exempts_exactly_the_content_types_content_gate_can_assess(self) -> None:
        """Pins the *content-type* set this module skips against the upstream one.

        Deliberately named for what it actually checks. It does **not** prove the two gates
        partition anything: `assess_legal_text_density` is only reached by the three
        providers that inherit `PortalHttpProviderBase`, so HTML/XML from ~10 of 13
        providers — Fedlex and Gemeinde among them — is marker-checked by neither gate. That
        hole is keyed on provider class, is invisible to this assertion, and is written down
        in the module docstring instead. An earlier version of this test was named for a
        partition that does not exist, which would have let the gap widen under a green run.
        """
        source = self._content_gate_source()
        match = re.search(r"_ASSESSABLE_CONTENT_TYPES = frozenset\(\s*\{(.*?)\}", source, re.DOTALL)
        self.assertIsNotNone(match)
        upstream = set(re.findall(r"\"([^\"]+)\"", match.group(1)))
        self.assertEqual(upstream, set(UPSTREAM_ASSESSED_CONTENT_TYPES))


class MunicipalLawHeadroomTests(unittest.TestCase):
    """The floors must admit the *shortest real law the repo holds*, not just a cantonal act.

    These two documents are in-force municipal dog-tax decisions — the municipal rung of
    ADR-0033's own dog question — captured as `application/pdf` via `lexfind_api`, so they
    take exactly the `below_content_floor` path this gate added. At the original floor of 3
    markers they sat *exactly on* it, and their third marker was the word `Artikel` inside
    LexFind's change-table boilerplate. Any rendering without that table withheld genuine
    law. This is the regression test for that.
    """

    @classmethod
    def setUpClass(cls) -> None:
        payload = json.loads(_MUNICIPAL_FIXTURE.read_text(encoding="utf-8"))
        cls.documents = payload["documents"]

    def _assert_admitted(self, text: str, label: str) -> None:
        verdict = assess_quarantine(normalized_document=_ir(text), content_type="application/pdf")
        self.assertFalse(
            verdict.quarantined,
            f"{label} is real law in force and was withheld: {verdict.reason} — {verdict.detail}",
        )

    def test_real_municipal_ordinances_are_admitted(self) -> None:
        for key, document in self.documents.items():
            with self.subTest(document=key):
                self._assert_admitted(document["text"], document["title"])

    def test_they_are_still_admitted_without_the_lexfind_change_table(self) -> None:
        """The headroom has to survive the boilerplate going away.

        `Änderungstabelle - Nach Artikel` is furniture, and the `Artikel` in it is why these
        documents scored 3 rather than their genuine 2. A first-enactment record, another
        canton's template, or a marginalia filter that drops the table must not turn a
        published ordinance into a quarantined one.
        """
        for key, document in self.documents.items():
            with self.subTest(document=key):
                body = document["text"].split("Änderungstabelle")[0]
                self.assertIn("Änderungstabelle", document["text"], "fixture no longer has the table")
                self.assertEqual(
                    count_legal_markers(body),
                    2,
                    "the genuine structural-marker count of these ordinances changed; "
                    "re-derive the floor before touching it",
                )
                self._assert_admitted(body, f"{document['title']} (change table stripped)")

    def test_the_floor_still_refuses_a_zero_marker_interstitial(self) -> None:
        """Lowering the floor must not make it decorative: the population it separates is
        real law (>= 2 markers measured) from chrome (0 measured)."""
        interstitial = (
            "Diese Website verwendet Cookies, um Ihnen die bestmoegliche Nutzung zu "
            "ermoeglichen. Bitte bestaetigen Sie Ihre Auswahl, bevor Sie fortfahren. "
            "Weitere Informationen finden Sie in unserer Datenschutzerklaerung sowie "
            "in den Nutzungsbedingungen dieses Portals."
        )
        verdict = assess_quarantine(normalized_document=_ir(interstitial), content_type="application/pdf")
        self.assertTrue(verdict.quarantined)
        self.assertEqual(verdict.reason, "below_content_floor")


class QuarantinePipelineTests(unittest.TestCase):
    def _process_pdf(self, pdf_bytes: bytes, *, di_overrides: dict | None = None):
        with tempfile.NamedTemporaryFile("wb", suffix=".pdf", delete=False) as pdf_handle:
            pdf_handle.write(pdf_bytes)
            artifact_path = pdf_handle.name

        payload = build_manifest_payload(
            artifact_path,
            artifact_role="primary_document",
            content_type="application/pdf",
            parser_hints=_PDF_PARSER_HINTS,
        )
        if di_overrides is not None:
            payload["di_overrides"] = di_overrides

        with tempfile.NamedTemporaryFile("w", suffix=".json", delete=False) as manifest_handle:
            json.dump(payload, manifest_handle)
            manifest_path = manifest_handle.name

        sink = InMemoryCanonicalSink()
        try:
            result = ProcessingPipeline(sink=sink, processing_version="di_2026_09_03").process_event(
                build_bundle_event(manifest_path)
            )
        finally:
            os.unlink(artifact_path)
            os.unlink(manifest_path)
        return result, sink

    def test_valid_pdf_with_no_text_layer_is_quarantined_and_publishes_nothing(self) -> None:
        pdf_bytes = _image_only_pdf()
        # The artifact really is a well-formed PDF: this is the case no byte-level guard
        # can catch, which is why the assertion has to live after extraction.
        self.assertTrue(pdf_bytes.startswith(b"%PDF-"))
        self.assertTrue(normalize_pdf_document(pdf_bytes, "art_1").metadata.get("pdf_no_text_layer"))

        result, sink = self._process_pdf(pdf_bytes)

        self.assertTrue(result.is_quarantined)
        self.assertIsNone(result.document)
        self.assertIsNone(result.document_processed_event)
        self.assertEqual(result.sections, [])
        # Nothing reached the canonical surfaces, and nothing reached legal-search.
        self.assertEqual(sink.published_documents, [])
        self.assertEqual(sink.published_sections, [])
        self.assertEqual(sink.document_processed_events, [])
        # The status flow stops before `canonical_ready` — it never became canonical.
        self.assertEqual(
            [event["payload"]["status"] for event in result.status_events],
            ["accepted", "processing"],
        )

    def test_the_quarantine_reason_is_recorded_and_retrievable(self) -> None:
        result, sink = self._process_pdf(_image_only_pdf())

        self.assertEqual(len(sink.processing_manifests), 1)
        manifest = sink.processing_manifests[0]
        self.assertEqual(manifest.status, "quarantined")
        self.assertEqual(manifest.document_count, 0)
        self.assertEqual(manifest.section_count, 0)
        self.assertIsNone(manifest.failure)
        self.assertEqual(manifest.quarantine["reason"], "no_text_layer")
        self.assertIn("OCR", manifest.quarantine["detail"])
        self.assertEqual(result.quarantine, manifest.quarantine)
        # The row is contract-valid, so the operator surface can be built on it.
        validate_processing_manifest(manifest)

    def test_a_real_statute_pdf_is_not_quarantined(self) -> None:
        """The floors must not refuse genuine law. `zh_as_554_510.pdf` is the ZH
        Hundeverordnung — the cantonal rung of ADR-0033's dog question, and among the
        shorter real acts, so it is the honest worst case for a character floor."""
        result, sink = self._process_pdf(_REAL_STATUTE_PDF.read_bytes())

        self.assertFalse(result.is_quarantined)
        self.assertIsNotNone(result.document)
        self.assertEqual(result.document.title, "Vollzugsvorschriften zum Hundegesetz")
        self.assertEqual(len(sink.published_documents), 1)
        self.assertEqual(len(sink.document_processed_events), 1)
        self.assertEqual(
            [event["payload"]["status"] for event in result.status_events],
            ["accepted", "processing", "canonical_ready"],
        )

    def test_a_per_source_floor_from_di_overrides_reaches_the_gate(self) -> None:
        """Proves the **DI half** of ADR-0047's per-source lever, and only that half.

        Nothing in platform-control emits `di_overrides` — the key appears nowhere under
        `platform-control/src` — so no real bundle carries these floors today. This asserts
        that when a producer exists the value arrives at the gate; it is not evidence that
        an operator can narrow a floor per source. The only live control is the
        environment-wide `DI_QUARANTINE_MIN_*`.
        """
        result, sink = self._process_pdf(
            _REAL_STATUTE_PDF.read_bytes(),
            di_overrides={"quarantine_min_extracted_chars": 1_000_000},
        )

        self.assertTrue(result.is_quarantined)
        self.assertEqual(result.quarantine["reason"], "below_content_floor")
        self.assertEqual(result.quarantine["min_extracted_chars"], 1_000_000)
        self.assertEqual(sink.published_documents, [])


if __name__ == "__main__":
    unittest.main()
