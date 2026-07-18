"""Layout-aware PDF normalization into the shared intermediate representation.

Municipal Swiss law is largely PDF-only (#590, #584): the operative ordinance has no
HTML manifestation, so the pipeline must normalize the PDF *itself*. A naive text dump
(``pdftotext``, ``pdfplumber.extract_text`` with default flow) is **not acceptable
here**: the Amtliche Sammlung PDFs carry marginal headings ("Randtitel") in a left-hand
margin band, and a left-to-right / top-to-bottom reading order splices them into the
body sentence beside them — e.g.

    „die Führung des **Organisation** Hundeverzeichnisses"

That is silently corrupted legal text: it indexes, it searches, it looks fine, and it is
wrong. The regression test in ``tests/test_normalize_pdf.py`` pins exactly this failure.

This normaliser is therefore **layout-aware**: it uses word bounding boxes to detect
vertical gutters, separates the marginal-heading band from the body column, and only
then reconstructs reading order. A Randtitel becomes its own heading block (carrying an
anchor, exactly like a Fedlex ``<article id=…>`` heading in the HTML path), so sectioning,
citations and anchors work unchanged against the same :class:`NormalizedDocumentIR`.

Library choice — ``pdfplumber`` (see ADR draft ``docs/adr/0037``): pure-Python, MIT,
word-level coordinates, no ML model downloads, deterministic and reproducible in CI. The
alternative, ``docling``, is referenced in the repo but was never installed; it pulls a
multi-GB Torch stack and downloads models at runtime, which is neither reproducible in CI
nor justified for coordinate-based margin/column separation.
"""

from __future__ import annotations

import io
import re
from dataclasses import dataclass
from typing import Any

from document_intelligence.errors import ProcessingError
from document_intelligence.normalize.ir import Block, NormalizedDocumentIR

# Line grouping: words whose vertical mid-points sit within this many points of each
# other belong to the same visual line.
_LINE_TOLERANCE_PT = 3.0
# A body paragraph breaks when the vertical gap to the next line exceeds this multiple of
# the running line height (a blank line / stanza break in the source).
_PARAGRAPH_GAP_FACTOR = 1.8


@dataclass(frozen=True)
class _Word:
    text: str
    x0: float
    x1: float
    top: float
    bottom: float

    @property
    def cx(self) -> float:
        return (self.x0 + self.x1) / 2.0

    @property
    def cy(self) -> float:
        return (self.top + self.bottom) / 2.0

    @property
    def height(self) -> float:
        return max(1.0, self.bottom - self.top)


@dataclass(frozen=True)
class _Column:
    x0: float
    x1: float
    words: list[_Word]

    @property
    def cx(self) -> float:
        return (self.x0 + self.x1) / 2.0

    @property
    def char_count(self) -> int:
        return sum(len(w.text) for w in self.words)


def normalize_pdf_document(pdf_bytes: bytes, artifact_id: str) -> NormalizedDocumentIR:
    """Normalize a PDF byte payload into the shared IR, layout-aware.

    Marginal headings are separated from the body column by their x-position and emitted
    as heading blocks, so they never splice into the body text beside them.
    """
    pdfplumber = _import_pdfplumber()

    blocks: list[Block] = []
    order = 0
    title: str | None = None
    page_count = 0
    any_text = False

    with pdfplumber.open(io.BytesIO(pdf_bytes)) as pdf:
        for page in pdf.pages:
            page_count += 1
            words = _extract_words(page)
            if not words:
                continue
            any_text = True
            page_blocks = _blocks_for_page(
                words=words,
                page_width=float(page.width or 0.0),
                artifact_id=artifact_id,
                start_order=order,
            )
            for block in page_blocks:
                if title is None and block.type == "heading":
                    title = block.text
                blocks.append(block)
                order += 1

    metadata: dict[str, Any] = {
        "title": title,
        "language": None,
        "normalizer": "pdf_v1",
        "source_profile_ref": "default_pdf_v1",
        "normalization_profile_ref": "pdf_v1",
        "source_flavor": "layout_pdf",
        "pdf_page_count": page_count,
        "pdf_extractor": "pdfplumber",
        "pdf_layout_aware": True,
    }
    if not any_text:
        # A scanned / image-only PDF has no text layer. Emitting an empty IR is the
        # honest outcome — better than fabricating body text — and flags the artifact
        # as needing OCR downstream rather than silently normalising nothing.
        metadata["pdf_no_text_layer"] = True

    return NormalizedDocumentIR(blocks=blocks, metadata=metadata)


def _blocks_for_page(
    *,
    words: list[_Word],
    page_width: float,
    artifact_id: str,
    start_order: int,
) -> list[Block]:
    columns = _detect_columns(words, page_width)
    if not columns:
        return []

    body_column = max(columns, key=lambda c: (c.char_count, c.x1 - c.x0))
    # Marginal-heading bands are the columns entirely to the left of the body column
    # (Swiss Randtitel convention). Anything to the right of the body (page numbers,
    # stray footnote marks) is dropped from the reading flow rather than spliced in.
    marginal_columns = [c for c in columns if c is not body_column and c.x1 <= body_column.x0 + 1.0]

    body_lines = _group_lines(body_column.words)
    marginal_lines = [line for column in marginal_columns for line in _group_lines(column.words)]

    return _interleave(
        body_lines=body_lines,
        marginal_lines=marginal_lines,
        artifact_id=artifact_id,
        start_order=start_order,
    )


@dataclass
class _Line:
    text: str
    top: float
    bottom: float
    height: float

    @property
    def cy(self) -> float:
        return (self.top + self.bottom) / 2.0


def _group_lines(words: list[_Word]) -> list[_Line]:
    """Group a column's words into visual lines, ordered top-to-bottom."""
    if not words:
        return []
    ordered = sorted(words, key=lambda w: (round(w.cy, 1), w.x0))
    lines: list[list[_Word]] = []
    current: list[_Word] = [ordered[0]]
    current_cy = ordered[0].cy
    for word in ordered[1:]:
        if abs(word.cy - current_cy) <= _LINE_TOLERANCE_PT:
            current.append(word)
            # Track the running centre so a gently sloping baseline still coheres.
            current_cy = sum(w.cy for w in current) / len(current)
        else:
            lines.append(current)
            current = [word]
            current_cy = word.cy
    lines.append(current)

    result: list[_Line] = []
    for line_words in lines:
        line_words.sort(key=lambda w: w.x0)
        text = _normalize_whitespace(" ".join(w.text for w in line_words))
        if not text:
            continue
        top = min(w.top for w in line_words)
        bottom = max(w.bottom for w in line_words)
        height = sum(w.height for w in line_words) / len(line_words)
        result.append(_Line(text=text, top=top, bottom=bottom, height=height))
    result.sort(key=lambda line: line.top)
    return result


@dataclass
class _Paragraph:
    text: str
    top: float
    bottom: float


def _paragraphs_from_body(body_lines: list[_Line]) -> list[_Paragraph]:
    """Coalesce body lines into paragraphs using vertical gaps only.

    Marginal headings are ignored here: a Randtitel labels a provision but must never
    break the provision's sentence, so paragraph boundaries come solely from the body
    column's own line spacing.
    """
    paragraphs: list[_Paragraph] = []
    buffer: list[str] = []
    top = 0.0
    bottom = 0.0
    prev_bottom: float | None = None
    prev_height: float | None = None

    def _flush() -> None:
        nonlocal buffer
        if buffer:
            paragraphs.append(_Paragraph(text=_normalize_whitespace(" ".join(buffer)), top=top, bottom=bottom))
            buffer = []

    for line in body_lines:
        if prev_bottom is not None:
            gap = line.top - prev_bottom
            reference = prev_height or line.height
            if gap > reference * _PARAGRAPH_GAP_FACTOR:
                _flush()
        if not buffer:
            top = line.top
        buffer.append(line.text)
        bottom = line.bottom
        prev_bottom = line.bottom
        prev_height = line.height
    _flush()
    return paragraphs


def _interleave(
    *,
    body_lines: list[_Line],
    marginal_lines: list[_Line],
    artifact_id: str,
    start_order: int,
) -> list[Block]:
    """Emit body paragraphs with marginal headings attached to the provision they label.

    A Randtitel is emitted as a heading block **before** the whole body paragraph whose
    vertical span it sits within — never spliced into that paragraph's sentence. This is
    the exact corruption #590 exists to prevent.
    """
    blocks: list[Block] = []
    order = start_order

    def _emit(block_type: str, text: str, level: int | None, anchor: str | None) -> None:
        nonlocal order
        if not text:
            return
        attrs: dict[str, Any] = {"tag": "pdf"}
        if anchor:
            attrs["anchor"] = anchor
        blocks.append(
            Block(
                id=f"blk_{order:04d}",
                type=block_type,
                text=text,
                level=level,
                order=order,
                parent_id=None,
                artifact_id=artifact_id,
                attrs=attrs,
            )
        )
        order += 1

    paragraphs = _paragraphs_from_body(body_lines)
    marginals = sorted(marginal_lines, key=lambda line: line.cy)

    if not paragraphs:
        # No body text: still surface the marginal headings rather than dropping them.
        for marginal in marginals:
            _emit("heading", marginal.text, 3, _slugify(marginal.text))
        return blocks

    # Assign each marginal heading to the paragraph whose vertical span best contains it
    # (or the nearest following paragraph when it sits in the leading above the block).
    attached: dict[int, list[_Line]] = {i: [] for i in range(len(paragraphs))}

    def _paragraph_for(marginal: _Line) -> int:
        cy = marginal.cy
        for index, para in enumerate(paragraphs):
            if para.top - _LINE_TOLERANCE_PT <= cy <= para.bottom + _LINE_TOLERANCE_PT:
                return index
        # Not inside any paragraph — attach to the first paragraph starting at/after it.
        for index, para in enumerate(paragraphs):
            if para.top >= cy:
                return index
        return len(paragraphs) - 1

    for marginal in marginals:
        attached[_paragraph_for(marginal)].append(marginal)

    for index, para in enumerate(paragraphs):
        for marginal in attached[index]:
            _emit("heading", marginal.text, 3, _slugify(marginal.text))
        _emit("paragraph", para.text, None, None)

    return blocks


def _detect_columns(words: list[_Word], page_width: float) -> list[_Column]:
    """Split a page's words into vertical columns separated by whitespace gutters.

    Words are projected onto the x-axis; their bounding intervals are merged with a small
    join tolerance. Runs of merged coverage are columns; the whitespace between them are
    gutters. A join tolerance larger than intra-column word spacing but smaller than a
    margin gutter keeps the Randtitel band separate from the body column.
    """
    if not words:
        return []
    # Join tolerance scales with page width so it holds across A4 / Letter / cropped pages.
    join_tol = max(18.0, page_width * 0.04) if page_width else 18.0

    ordered = sorted(words, key=lambda w: w.x0)
    bands: list[list[float]] = [[ordered[0].x0, ordered[0].x1]]
    for word in ordered[1:]:
        current = bands[-1]
        if word.x0 - current[1] <= join_tol:
            current[1] = max(current[1], word.x1)
        else:
            bands.append([word.x0, word.x1])

    if len(bands) == 1:
        return [_Column(x0=bands[0][0], x1=bands[0][1], words=list(words))]

    columns: list[_Column] = []
    for x0, x1 in bands:
        band_words = [w for w in words if x0 - 0.5 <= w.cx <= x1 + 0.5]
        if band_words:
            columns.append(_Column(x0=x0, x1=x1, words=band_words))
    return columns


def _extract_words(page: Any) -> list[_Word]:
    raw = page.extract_words(
        use_text_flow=False,
        keep_blank_chars=False,
        x_tolerance=1.5,
        y_tolerance=1.5,
    )
    words: list[_Word] = []
    for item in raw:
        text = str(item.get("text", "")).strip()
        if not text:
            continue
        words.append(
            _Word(
                text=text,
                x0=float(item["x0"]),
                x1=float(item["x1"]),
                top=float(item["top"]),
                bottom=float(item["bottom"]),
            )
        )
    return words


def _import_pdfplumber() -> Any:
    try:
        import pdfplumber
    except ImportError as error:  # pragma: no cover - exercised only without the extra
        raise ProcessingError(
            "missing_pdf_dependency",
            "pdfplumber is required to normalise application/pdf artifacts; install the "
            "'pdf' extra (pip install -e '.[pdf]').",
        ) from error
    return pdfplumber


_SLUG_RE = re.compile(r"[^a-z0-9]+")


def _slugify(value: str) -> str | None:
    slug = _SLUG_RE.sub("_", value.strip().lower()).strip("_")
    return slug or None


def _normalize_whitespace(value: str) -> str:
    return " ".join(value.split())
