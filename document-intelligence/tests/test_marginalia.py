"""Randtitel detection and body/margin partition, measured against the real ordinance.

``tests/test_normalize_pdf.py`` used a *synthetic* reportlab fixture with the marginal
heading in the **left** margin and a generous gutter. That is why ADR-0037's normaliser
shipped green while corrupting the real document: the real Zurich ordinance (AS 554.510)
puts the Randtitel on the **right** on recto pages, with a 5.6pt gutter — narrower than
p90 intra-sentence word spacing (6.5pt).

The fixture here is therefore the **real PDF**, committed at
``tests/fixtures/zh_as_554_510.pdf``. Swiss official texts carry no copyright (Art. 5 URG).
"""

from __future__ import annotations

import io
from pathlib import Path

import pytest

from document_intelligence.normalize.marginalia import (
    detect_marginal_blocks,
    extract_page_words,
    join_wrapped_lines,
    split_page_words,
)

pytest.importorskip("pdfplumber")

_FIXTURE = Path(__file__).parent / "fixtures" / "zh_as_554_510.pdf"

# Every Randtitel in AS 554.510, in reading order, with the page and band side it sits in.
# Page 1 (recto) carries them on the right, page 2 (verso) on the left — the ordinance is
# set as a booklet, which ADR-0037's left-only band search could never have handled.
_EXPECTED = [
    (1, "Organisation", "right"),
    (1, "Abgabe an die Gemeinde und Kantonsbeitrag", "right"),
    (1, "Ermässigung Kursbesuch", "right"),
    (1, "Härtefall", "right"),
    (2, "Gebühren", "left"),
    (2, "Zuständigkeiten", "left"),
    (2, "Aufhebung bisherigen Rechts", "left"),
    (2, "Inkrafttreten", "left"),
]


def _pdf_bytes() -> bytes:
    return _FIXTURE.read_bytes()


def test_real_ordinance_marginal_bands_are_detected() -> None:
    blocks = detect_marginal_blocks(_pdf_bytes())
    assert [(b.page_no, b.text, b.side) for b in blocks] == _EXPECTED


def test_wrapped_randtitel_is_dehyphenated() -> None:
    # "Aufhebung bis-" / "herigen Rechts" wraps inside the narrow band. Unless the two
    # lines rejoin as one word, the lifted heading is not the label the document carries.
    blocks = detect_marginal_blocks(_pdf_bytes())
    texts = [b.text for b in blocks]
    assert "Aufhebung bisherigen Rechts" in texts
    assert not any("bis- herigen" in t for t in texts)


def test_band_words_are_removed_from_the_body_stream() -> None:
    """The partition is set subtraction, not string matching.

    This is the property that makes the splice impossible rather than repaired: once the
    band's words are gone from the word stream, no downstream layout pass can put them
    back inside a sentence.
    """
    import pdfplumber

    with pdfplumber.open(io.BytesIO(_pdf_bytes())) as pdf:
        page = pdf.pages[0]
        words = extract_page_words(page)
        split = split_page_words(words=words, page_width=float(page.width), page_no=1)

    body_text = " ".join(w.text for w in split.body_words)
    assert "Organisation" not in body_text
    assert "Härtefall" in body_text, "the word occurs in the body too and must survive there"
    assert len(split.body_words) < len(words)
    # Nothing is invented and nothing is lost: body + band accounts for every word.
    band_word_count = sum(len(b.text.split()) for b in split.marginal_blocks)
    assert len(split.body_words) + band_word_count == len(words)


def test_single_column_document_yields_no_marginal_blocks() -> None:
    # The guards must not invent Randtitel in an ordinary one-column PDF.
    reportlab_canvas = pytest.importorskip("reportlab.pdfgen.canvas")

    from reportlab.lib.pagesizes import A4

    buffer = io.BytesIO()
    canvas = reportlab_canvas.Canvas(buffer, pagesize=A4)
    canvas.setFont("Helvetica", 11)
    for index, line in enumerate(
        [
            "Der Gemeinderat erlaesst gestuetzt auf das kantonale",
            "Hundegesetz die folgenden Vollzugsvorschriften fuer",
            "das Gemeindegebiet und die Hundekontrolle.",
        ]
    ):
        canvas.drawString(80, A4[1] - 100 - index * 18, line)
    canvas.showPage()
    canvas.save()

    assert detect_marginal_blocks(buffer.getvalue()) == []


def test_two_column_body_is_not_shredded_into_headings() -> None:
    # A genuine two-column layout must fail the band guards. Mistaking a body column for
    # a margin would corrupt far more text than the splice this module prevents.
    reportlab_canvas = pytest.importorskip("reportlab.pdfgen.canvas")

    from reportlab.lib.pagesizes import A4

    buffer = io.BytesIO()
    canvas = reportlab_canvas.Canvas(buffer, pagesize=A4)
    canvas.setFont("Helvetica", 11)
    for index in range(20):
        y = A4[1] - 100 - index * 16
        canvas.drawString(60, y, "Die Gemeinde ist zustaendig fuer die Fuehrung")
        canvas.drawString(320, y, "des Verzeichnisses und der Kontrolle im Gebiet")
    canvas.showPage()
    canvas.save()

    assert detect_marginal_blocks(buffer.getvalue()) == []


def test_right_aligned_fee_column_is_not_a_marginal_band() -> None:
    """A right-aligned amount is body content, not a Randtitel.

    This is what makes *line starts* the right signal rather than word positions: the
    amounts sit far right on every line, but they never *begin* a line, so they form no
    line-start cluster. A word-position signal would see a column here and shred the
    fee table into headings.
    """
    reportlab_canvas = pytest.importorskip("reportlab.pdfgen.canvas")

    from reportlab.lib.pagesizes import A4

    buffer = io.BytesIO()
    canvas = reportlab_canvas.Canvas(buffer, pagesize=A4)
    canvas.setFont("Helvetica", 11)
    for index in range(15):
        y = A4[1] - 100 - index * 16
        canvas.drawString(80, y, f"Einschreibegebuehr bei Neueintragung Position {index}")
        canvas.drawString(470, y, "Fr. 20.-")
    canvas.showPage()
    canvas.save()

    assert detect_marginal_blocks(buffer.getvalue()) == []


def test_hyphen_healing_keeps_an_elided_compound() -> None:
    # "Halter- und Hundedaten" is an elision, not a wrap: healing it would fabricate the
    # word "Halterund". The conjunction is the signal that distinguishes the two.
    assert join_wrapped_lines(["Halter-", "und Hundedaten"]) == "Halter- und Hundedaten"
    assert join_wrapped_lines(["Hundehaltungsvoraus-", "setzungen sind"]) == "Hundehaltungsvoraussetzungen sind"
