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

    def test_upstream_default_threshold_is_the_di_default(self) -> None:
        source = self._content_gate_source()
        match = re.search(r"DEFAULT_MIN_LEGAL_MARKERS = (\d+)", source)
        self.assertIsNotNone(match)
        self.assertEqual(int(match.group(1)), DEFAULT_MIN_LEGAL_MARKERS)

    def test_the_two_gates_partition_the_modality_space(self) -> None:
        """DI's floors cover exactly what `content_gate` abstains on. If the upstream set
        grows, this gate would start re-judging a modality acquisition now handles; if it
        shrinks, a modality would fall between the two and be judged by nobody."""
        source = self._content_gate_source()
        match = re.search(r"_ASSESSABLE_CONTENT_TYPES = frozenset\(\s*\{(.*?)\}", source, re.DOTALL)
        self.assertIsNotNone(match)
        upstream = set(re.findall(r"\"([^\"]+)\"", match.group(1)))
        self.assertEqual(upstream, set(UPSTREAM_ASSESSED_CONTENT_TYPES))


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
        """ADR-0047: floors are per-source config. A floor above the real ordinance
        withholds it, which proves the override is wired end to end — nothing else about
        this document changed."""
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
