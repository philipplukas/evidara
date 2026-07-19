"""Regression tests for the PDF normaliser (#590, #650).

**Read this before trusting a green run here.** The synthetic reportlab fixture below is
why the splice bug shipped: it puts the Randtitel in the **left** margin with a wide
gutter, which is not what the real document does. ADR-0037's x-projection normaliser
passes on it and corrupts the real ordinance.

The synthetic tests are retained — they still pin a real property — but the tests that
actually hold the line for #650 are the real-PDF ones at the bottom of this file and in
``tests/test_marginalia.py``. When in doubt, trust those.
"""

from __future__ import annotations

import io
from pathlib import Path

# reportlab is a declared dependency of the `test` extra, which every path that runs this
# suite installs (CI job, scripts/check-document-intelligence.sh, the documented local
# gate in CLAUDE.md). It is imported hard, not via `pytest.importorskip`, on purpose:
# these are the anti-corruption regression tests for #590/#650, and a module-level
# importorskip would silently delete the whole file from the run if the extra were ever
# dropped — reporting green over the exact tests that exist to catch text corruption.
# If this import fails, the environment is wrong and the suite should say so loudly.
from reportlab.lib.pagesizes import A4
from reportlab.pdfgen import canvas as reportlab_canvas

from document_intelligence.normalize.ir import NormalizedDocumentIR
from document_intelligence.normalize.pdf import normalize_pdf_document

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


# --- The real ordinance (AS 554.510) ------------------------------------------------
#
# Everything above this line runs against a synthetic fixture that the *broken* normaliser
# passes. These run against the committed real PDF, which it does not.

_REAL_PDF = Path(__file__).parent / "fixtures" / "zh_as_554_510.pdf"

# The splice as it appears in the real document, and the contiguous text it should be.
_REAL_SPLICE = "Führung des Organisation Hundeverzeichnisses"
_REAL_CLEAN = "Führung des Hundeverzeichnisses"


def test_real_ordinance_is_not_spliced() -> None:
    """The load-bearing regression test for #650.

    Fails on ADR-0037's x-projection normaliser, which collapses the page to one column
    (gutter 5.6pt < p90 word gap 6.5pt) and splices the Randtitel mid-sentence.
    """
    ir = normalize_pdf_document(_REAL_PDF.read_bytes(), artifact_id="art_zh")
    body = ir.body_text

    # 1. The provision's sentence is contiguous — the Randtitel is not inside it.
    assert _REAL_SPLICE not in body
    assert _REAL_CLEAN in body

    # 2. De-hyphenation across the line break. Without this a query for the compound
    #    cannot match the document at all — silent corruption of the same class as #643.
    assert "Hundehaltungsvoraussetzungen" in body
    assert "Hundehaltungsvoraus- setzungen" not in body
    assert "Kalenderjahr" in body
    assert "Gebührenrückerstattung" in body

    # 3. Every Randtitel is lifted into its own heading block, none left in a paragraph.
    assert ir.metadata["pdf_marginal_headings"] == 8
    headings = {b.text for b in ir.blocks if b.type == "heading"}
    assert {"Organisation", "Härtefall", "Inkrafttreten", "Aufhebung bisherigen Rechts"} <= headings
    assert all("Organisation" not in b.text for b in ir.blocks if b.type == "paragraph")

    organisation = next(b for b in ir.blocks if b.text == "Organisation")
    assert organisation.type == "heading"
    assert organisation.attrs.get("anchor") == "organisation"
    assert organisation.attrs.get("marginal") is True

    # 4. Document structure, recovered from type geometry rather than a layout model.
    assert ir.metadata["title"] == "Vollzugsvorschriften zum Hundegesetz"
    assert any(b.type == "heading" and b.text.startswith("A.") for b in ir.blocks)
    assert any(b.type == "list_item" for b in ir.blocks)


def test_running_headers_and_folios_stay_out_of_the_body() -> None:
    # The page furniture repeats on every page. Left in the flow it splices the document's
    # own title into the middle of a provision ("…in Kraft. 2 554.510 Vollzugs…").
    ir = normalize_pdf_document(_REAL_PDF.read_bytes(), artifact_id="art_furniture")
    paragraphs = [b.text for b in ir.blocks if b.type == "paragraph"]
    assert not any(t.strip() in {"1", "2", "554.510"} for t in paragraphs)
    assert sum(1 for b in ir.blocks if b.text == "Vollzugsvorschriften zum Hundegesetz") == 1


def test_wrapped_section_heading_is_one_block() -> None:
    # "B. Abgabe an die Gemeinde, Kantonsbeitrag und" / "Gebühren" is a single heading
    # that happens to wrap; split in two it reads as a section named "Gebühren".
    ir = normalize_pdf_document(_REAL_PDF.read_bytes(), artifact_id="art_wrap")
    headings = [b.text for b in ir.blocks if b.type == "heading"]
    assert "B. Abgabe an die Gemeinde, Kantonsbeitrag und Gebühren" in headings


def test_randtitel_heading_precedes_the_provision_it_labels() -> None:
    """Reading order, not just presence: the label must sit *before* its article."""
    ir = normalize_pdf_document(_REAL_PDF.read_bytes(), artifact_id="art_order")
    texts = [b.text for b in ir.blocks]

    for label, article in [
        ("Organisation", "Art. 1"),
        ("Abgabe an die Gemeinde und Kantonsbeitrag", "Art. 2"),
        ("Ermässigung Kursbesuch", "Art. 3"),
        ("Härtefall", "Art. 4"),
        ("Gebühren", "Art. 5"),
        ("Zuständigkeiten", "Art. 6"),
        ("Aufhebung bisherigen Rechts", "Art. 7"),
        ("Inkrafttreten", "Art. 8"),
    ]:
        article_index = next(i for i, t in enumerate(texts) if t.startswith(article))
        assert texts[article_index - 1] == label, f"{label} must directly precede {article}"
