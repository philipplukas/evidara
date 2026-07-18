"""Randtitel detection and lifting, measured against the real ordinance (ADR-0038).

``tests/test_normalize_pdf.py`` used a *synthetic* reportlab fixture with the marginal
heading in the **left** margin and a generous gutter. That is why ADR-0037's normaliser
shipped green while corrupting the real document: the real Zurich ordinance (AS 554.510)
puts the Randtitel on the **right** on recto pages, with a 5.6pt gutter — narrower than
p90 intra-sentence word spacing (6.5pt).

The fixture here is therefore the **real PDF**, committed at
``tests/fixtures/zh_as_554_510.pdf``. Swiss official texts carry no copyright (Art. 5 URG).
"""

from __future__ import annotations

from pathlib import Path

import pytest

from document_intelligence.normalize.ir import Block, NormalizedDocumentIR
from document_intelligence.normalize.marginalia import (
    detect_marginal_blocks,
    lift_marginal_headings,
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
    # lines rejoin as one word, the lifted heading cannot match the extractor's text.
    blocks = detect_marginal_blocks(_pdf_bytes())
    texts = [b.text for b in blocks]
    assert "Aufhebung bisherigen Rechts" in texts
    assert not any("bis- herigen" in t for t in texts)


def test_single_column_document_yields_no_marginal_blocks() -> None:
    # The guards must not invent Randtitel in an ordinary one-column PDF.
    reportlab_canvas = pytest.importorskip("reportlab.pdfgen.canvas")
    import io

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


def _block(order: int, text: str, *, page_no: int, top: float, bottom: float, block_type: str = "paragraph") -> Block:
    return Block(
        id=f"blk_{order:04d}",
        type=block_type,
        text=text,
        order=order,
        artifact_id="art_test",
        attrs={"page_no": page_no, "bbox_top": top, "bbox_bottom": bottom},
    )


def test_lift_strips_randtitel_appended_to_paragraph() -> None:
    """Docling's actual failure mode: the label is appended to the paragraph's END.

    Sentence integrity survives (docling never interleaves mid-clause), but the label
    still lands inside the body block, so it would index as body text.
    """
    ir = NormalizedDocumentIR(
        blocks=[
            _block(
                0,
                "Art. 1 1 Die Aufsicht über das Hundewesen, die Führung des "
                "Hundeverzeichnisses sind Sache des Sicherheitsdepartements. Organisation",
                page_no=1,
                top=302.0,
                bottom=372.0,
            )
        ],
        metadata={},
    )
    marginals = [b for b in detect_marginal_blocks(_pdf_bytes()) if b.text == "Organisation"]
    assert marginals, "fixture must contain the Organisation Randtitel"

    lifted, diagnostics = lift_marginal_headings(ir, marginals)

    assert diagnostics == {"detected": 1, "lifted": 1, "unmatched": []}
    assert [(b.type, b.text) for b in lifted.blocks][0] == ("heading", "Organisation")
    body = lifted.blocks[1]
    assert body.type == "paragraph"
    assert "Organisation" not in body.text
    assert body.text.endswith("Sache des Sicherheitsdepartements.")
    assert "Führung des Hundeverzeichnisses" in body.text


def test_lift_repositions_standalone_randtitel_into_reading_order() -> None:
    """Docling's second failure mode: page 2's labels are emitted after the last article.

    The label is not spliced, but it is in the wrong place — it must move to just before
    the provision it labels, or the heading structure is nonsense.
    """
    ir = NormalizedDocumentIR(
        blocks=[
            _block(0, "Art. 8 Diese Vollzugsvorschriften treten in Kraft.", page_no=2, top=629.0, bottom=657.0),
            _block(1, "Inkrafttreten", page_no=2, top=629.1, bottom=640.1),
        ],
        metadata={},
    )
    marginals = [b for b in detect_marginal_blocks(_pdf_bytes()) if b.text == "Inkrafttreten"]
    assert marginals

    lifted, diagnostics = lift_marginal_headings(ir, marginals)

    assert diagnostics["lifted"] == 1
    assert [(b.type, b.text) for b in lifted.blocks] == [
        ("heading", "Inkrafttreten"),
        ("paragraph", "Art. 8 Diese Vollzugsvorschriften treten in Kraft."),
    ]
    assert [b.order for b in lifted.blocks] == [0, 1]


def test_lift_never_strips_text_from_an_unrelated_page() -> None:
    # Geometry gates every match: a phrase that recurs on another page must survive.
    ir = NormalizedDocumentIR(
        blocks=[_block(0, "Ein Satz über die Organisation der Kontrolle.", page_no=2, top=10.0, bottom=30.0)],
        metadata={},
    )
    marginals = [b for b in detect_marginal_blocks(_pdf_bytes()) if b.text == "Organisation"]

    lifted, diagnostics = lift_marginal_headings(ir, marginals)

    assert diagnostics["lifted"] == 0
    assert diagnostics["unmatched"] == ["Organisation"]
    assert lifted.blocks[0].text == "Ein Satz über die Organisation der Kontrolle."
