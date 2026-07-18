"""Regression tests for the layout-aware PDF normaliser (#590).

The load-bearing test is ``test_marginal_heading_is_not_spliced_into_body``: it builds a
synthetic multi-column PDF that reproduces the *exact* failure mode from the issue — a
marginal heading ("Randtitel") that a naive top-to-bottom text dump splices into the body
sentence beside it, silently corrupting legal text:

    „die Führung des **Organisation** Hundeverzeichnisses"

We could not obtain the real Zurich ordinance PDF (AS 554.510) in the sandbox, so the
fixture is synthetic — but it reproduces the marginal-splice mode deterministically: the
test first asserts that a naive extraction *does* splice (proving the fixture is faithful),
then asserts the layout-aware normaliser does not.
"""

from __future__ import annotations

import io

import pytest

from document_intelligence.normalize.ir import NormalizedDocumentIR
from document_intelligence.normalize.pdf import normalize_pdf_document

reportlab_canvas = pytest.importorskip("reportlab.pdfgen.canvas")
from reportlab.lib.pagesizes import A4  # noqa: E402

_PAGE_WIDTH, _PAGE_HEIGHT = A4
_BODY_X = 200.0
_MARGIN_X = 45.0

# The corrupted string a naive reader produces, and the clean body it should be.
# ASCII transliteration (Fuehrung/zustaendig) keeps the reportlab-drawn fixture and the
# assertions byte-identical; the real ordinance uses the umlaut form in the issue title.
_SPLICED = "des Organisation Hundeverzeichnisses"
_CLEAN_BODY_FRAGMENT = "die Fuehrung des Hundeverzeichnisses"


def _draw(canvas, x: float, y_top: float, text: str, *, font: str = "Helvetica", size: int = 11):
    canvas.setFont(font, size)
    # reportlab's origin is bottom-left; our coordinates are measured from the top.
    canvas.drawString(x, _PAGE_HEIGHT - y_top, text)


def _build_marginal_splice_pdf() -> bytes:
    """A single page whose body sentence is broken across lines, with a Randtitel
    ("Organisation") sitting in the left margin between two of those lines.

    A top-to-bottom reader emits the margin word between the body lines, splicing it into
    the sentence. A layout-aware reader separates the margin band by its x-position.
    """
    buffer = io.BytesIO()
    canvas = reportlab_canvas.Canvas(buffer, pagesize=A4)

    _draw(canvas, _BODY_X, 90, "Art. 4  Hundeverzeichnis", font="Helvetica-Bold", size=12)
    _draw(canvas, _BODY_X, 120, "Die Gemeinde ist zustaendig fuer")
    _draw(canvas, _BODY_X, 138, "die Fuehrung des")
    # Randtitel in the left margin, vertically between the two body lines below.
    _draw(canvas, _MARGIN_X, 150, "Organisation", font="Helvetica-Bold", size=9)
    _draw(canvas, _BODY_X, 156, "Hundeverzeichnisses und der")
    _draw(canvas, _BODY_X, 174, "Hundekontrolle im Gemeindegebiet.")

    canvas.showPage()
    canvas.save()
    return buffer.getvalue()


def _naive_extract_text(pdf_bytes: bytes) -> str:
    """A deliberately naive baseline: pdfplumber's default top-to-bottom text flow.

    This is the ``pdftotext``-equivalent the issue warns against — it has no notion of the
    margin band and reads strictly by vertical then horizontal position.
    """
    import pdfplumber

    with pdfplumber.open(io.BytesIO(pdf_bytes)) as pdf:
        raw = "\n".join(page.extract_text() or "" for page in pdf.pages)
    return " ".join(raw.split())


def test_naive_extraction_reproduces_the_splice() -> None:
    # Sanity: the fixture is faithful — a naive reader really does corrupt the sentence.
    pdf_bytes = _build_marginal_splice_pdf()
    assert _SPLICED in _naive_extract_text(pdf_bytes)


def test_marginal_heading_is_not_spliced_into_body() -> None:
    pdf_bytes = _build_marginal_splice_pdf()

    ir = normalize_pdf_document(pdf_bytes, artifact_id="art_dogpdf")

    paragraphs = [b for b in ir.blocks if b.type == "paragraph"]
    headings = [b for b in ir.blocks if b.type == "heading"]

    # No paragraph is contaminated by the margin word: the sentence survives intact in a
    # single body block, and the corrupted splice appears in none of them.
    assert any(_CLEAN_BODY_FRAGMENT in p.text for p in paragraphs)
    assert all(_SPLICED not in p.text for p in paragraphs)
    assert all("Organisation" not in p.text for p in paragraphs)

    # The Randtitel is preserved — as its own addressable heading block, not discarded
    # and not spliced. It carries a stable anchor exactly like the HTML article path.
    assert any(b.text == "Organisation" for b in headings)
    organisation = next(b for b in headings if b.text == "Organisation")
    assert organisation.attrs.get("anchor") == "organisation"


def test_pdf_ir_metadata_marks_layout_aware() -> None:
    ir = normalize_pdf_document(_build_marginal_splice_pdf(), artifact_id="art_meta")
    assert isinstance(ir, NormalizedDocumentIR)
    assert ir.metadata["normalizer"] == "pdf_v1"
    assert ir.metadata["pdf_layout_aware"] is True
    assert ir.metadata["pdf_extractor"] == "pdfplumber"
    assert ir.metadata["pdf_page_count"] == 1
    assert "pdf_no_text_layer" not in ir.metadata


def test_single_column_pdf_reads_as_one_paragraph() -> None:
    buffer = io.BytesIO()
    canvas = reportlab_canvas.Canvas(buffer, pagesize=A4)
    _draw(canvas, 80, 100, "Der Gemeinderat erlaesst gestuetzt auf")
    _draw(canvas, 80, 118, "das kantonale Hundegesetz folgende")
    _draw(canvas, 80, 136, "Vollzugsvorschriften.")
    canvas.showPage()
    canvas.save()

    ir = normalize_pdf_document(buffer.getvalue(), artifact_id="art_single")
    body = ir.body_text
    assert "Der Gemeinderat erlaesst gestuetzt auf das kantonale Hundegesetz" in body


def test_pdf_without_text_layer_is_flagged_not_fabricated() -> None:
    # An image-only page (no drawn text) must yield an empty IR flagged for OCR, never
    # fabricated body text.
    buffer = io.BytesIO()
    canvas = reportlab_canvas.Canvas(buffer, pagesize=A4)
    canvas.rect(100, 100, 200, 200, fill=1)
    canvas.showPage()
    canvas.save()

    ir = normalize_pdf_document(buffer.getvalue(), artifact_id="art_scan")
    assert ir.blocks == []
    assert ir.metadata["pdf_no_text_layer"] is True
