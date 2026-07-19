"""Layout-aware PDF normalization into the shared intermediate representation.

Municipal Swiss law is largely PDF-only (#590, #584): the operative ordinance has no HTML
manifestation, so the pipeline must normalize the PDF *itself*. A naive text dump
(``pdftotext``, ``pdfplumber.extract_text`` with default flow) is **not acceptable here**:
the Amtliche Sammlung PDFs carry marginal headings ("Randtitel") in a band beside the body,
and a top-to-bottom reading order splices them into the body sentence —

    „die Führung des **Organisation** Hundeverzeichnisses"

That is silently corrupted legal text: it indexes, it searches, it looks fine, and it is
wrong.

**The fix is geometric, not a better extractor** (ADR-0038, amending ADR-0037 §3).
``normalize/marginalia.py`` decides which words on a page are marginal; this module
subtracts them from the word stream and lays out what remains. Subtracting the band leaves
an ordinary single column behind, so reading order becomes trivial and the splice is
impossible by construction rather than repaired after the fact.

ADR-0037's own margin detector projected words onto the x-axis and split on whitespace
gutters. Measured on the real ordinance (Zurich AS 554.510) that signal does not exist —
the gutter is 5.6pt against a p90 intra-sentence word gap of 6.5pt — and it only ever
looked *left* of the body while the booklet layout puts recto Randtitel on the right.
Both defects are fixed here; see ``marginalia`` for the signal that replaced it.
"""

from __future__ import annotations

import io
import re
from collections import Counter
from dataclasses import dataclass
from typing import Any

from document_intelligence.errors import ProcessingError
from document_intelligence.normalize.ir import Block, NormalizedDocumentIR
from document_intelligence.normalize.marginalia import (
    MarginalBlock,
    Word,
    extract_page_words,
    group_lines,
    join_wrapped_lines,
    split_page_words,
)

# Running headers and folios sit in the outermost slice of the page. Anything wholly
# inside these bands is furniture, not text: emitting it splices the document's own title
# and page numbers into the body ("…in Kraft. 2 554.510 Vollzugsvorschriften…").
_HEADER_BAND_RATIO = 0.08
_FOOTER_BAND_RATIO = 0.92
# A new paragraph starts when the baseline-to-baseline step exceeds this multiple of the
# page's own modal line pitch. Measured on AS 554.510: pitch 14.0pt, within-paragraph
# steps 14.0-14.7, between-paragraph steps 20.7-25.6.
_PARAGRAPH_PITCH_FACTOR = 1.4
# Type smaller than this fraction of the body size is apparatus (footnotes), not body.
_FOOTNOTE_SIZE_RATIO = 0.85
# Swiss legal literas: "a. Abgabe an die Gemeinde…". Deliberately narrow — a numeric
# pattern would swallow body lines that merely begin with a year or an article number.
_LIST_MARKER_RE = re.compile(r"^[a-z]\.\s")


@dataclass(frozen=True)
class _Line:
    words: list[Word]

    @property
    def text(self) -> str:
        return " ".join(w.text for w in self.words)

    @property
    def top(self) -> float:
        return min(w.top for w in self.words)

    @property
    def bottom(self) -> float:
        return max(w.bottom for w in self.words)

    @property
    def size(self) -> float:
        """The dominant type size — the tallest word, ignoring superscript apparatus."""
        return max(w.size for w in self.words)

    @property
    def bold(self) -> bool:
        significant = [w for w in self.words if w.size >= self.size - 0.5]
        return bool(significant) and all(w.bold for w in significant)


@dataclass
class _Section:
    """A run of body lines that will become one IR block."""

    type: str
    lines: list[_Line]
    level: int | None = None

    @property
    def top(self) -> float:
        return min(line.top for line in self.lines)

    @property
    def bottom(self) -> float:
        return max(line.bottom for line in self.lines)

    @property
    def text(self) -> str:
        return join_wrapped_lines(line.text for line in self.lines)


def normalize_pdf_document(pdf_bytes: bytes, artifact_id: str) -> NormalizedDocumentIR:
    """Normalize a PDF byte payload into the shared IR, layout-aware.

    Marginal headings are lifted into their own heading blocks *preceding* the provision
    they label, hyphenation across line breaks is healed, and running headers/folios are
    dropped from the reading flow.
    """
    pdfplumber = _import_pdfplumber()

    blocks: list[Block] = []
    title: str | None = None
    page_count = 0
    any_text = False
    marginal_total = 0

    with pdfplumber.open(io.BytesIO(pdf_bytes)) as pdf:
        for index, page in enumerate(pdf.pages):
            page_count += 1
            page_no = index + 1
            words = extract_page_words(page)
            if not words:
                continue
            any_text = True

            split = split_page_words(
                words=words,
                page_width=float(page.width or 0.0),
                page_no=page_no,
            )
            marginal_total += len(split.marginal_blocks)

            sections = _sections_for_page(
                body_words=split.body_words,
                page_height=float(page.height or 0.0),
            )
            page_blocks = _emit_page(
                sections=sections,
                marginal_blocks=split.marginal_blocks,
                artifact_id=artifact_id,
                page_no=page_no,
                start_order=len(blocks),
            )
            for block in page_blocks:
                if title is None and block.type == "heading" and not block.attrs.get("marginal"):
                    title = block.text
                blocks.append(block)

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
        "pdf_marginal_headings": marginal_total,
    }
    if not any_text:
        # A scanned / image-only PDF has no text layer. Emitting an empty IR is the
        # honest outcome — better than fabricating body text — and flags the artifact
        # as needing OCR downstream rather than silently normalising nothing.
        metadata["pdf_no_text_layer"] = True

    return NormalizedDocumentIR(blocks=blocks, metadata=metadata)


def _sections_for_page(*, body_words: list[Word], page_height: float) -> list[_Section]:
    """Lay out one page's body words into typed sections, in reading order."""
    lines = [_Line(words=line) for line in group_lines(body_words)]
    lines = [line for line in lines if line.text.strip()]
    if page_height:
        header = page_height * _HEADER_BAND_RATIO
        footer = page_height * _FOOTER_BAND_RATIO
        lines = [line for line in lines if line.bottom > header and line.top < footer]
    if not lines:
        return []

    body_size = _modal_size(lines)
    pitch = _modal_pitch(lines)

    # Footnote apparatus is the trailing run of small type at the foot of the page. It is
    # kept (it carries the legal citations) but never merged into a body paragraph.
    body_lines = list(lines)
    footnotes: list[_Line] = []
    while body_lines and body_lines[-1].size < body_size * _FOOTNOTE_SIZE_RATIO:
        footnotes.insert(0, body_lines.pop())

    sections: list[_Section] = []
    for line in body_lines:
        kind, level = _classify(line, body_size=body_size)
        previous = sections[-1] if sections else None
        # A wrapped continuation line keeps the type of the item it continues: the second
        # line of a litera ("(§ 17 Abs. 2 lit. a Hundeverordnung) Fr. 20.–;") is not a
        # paragraph of its own, and splitting it off would strip the litera of its content.
        adjacent = previous is not None and line.top - previous.bottom <= pitch * (_PARAGRAPH_PITCH_FACTOR - 1.0)
        if previous is None:
            starts_new = True
        elif kind == "heading" or previous.type == "heading":
            # A heading that wraps ("B. Abgabe an die Gemeinde, Kantonsbeitrag und" /
            # "Gebühren") is one heading, so an adjacent heading line of the same rank
            # continues it. Any other type change across a heading boundary breaks.
            starts_new = not (kind == "heading" and previous.type == "heading" and previous.level == level and adjacent)
        elif kind == "list_item":
            # `_classify` only returns list_item for a line carrying a litera marker, so
            # this is always the start of a new item — its continuations classify as
            # paragraphs and fall through to the adjacency rule below.
            starts_new = True
        else:
            starts_new = not adjacent
        if starts_new:
            sections.append(_Section(type=kind, lines=[line], level=level))
        else:
            previous.lines.append(line)

    for line in footnotes:
        sections.append(_Section(type="paragraph", lines=[line]))
    return sections


def _classify(line: _Line, *, body_size: float) -> tuple[str, int | None]:
    if line.bold and line.size >= body_size - 0.5:
        return "heading", 1 if line.size > body_size + 0.5 else 2
    if _LIST_MARKER_RE.match(line.text):
        return "list_item", None
    return "paragraph", None


def _modal_size(lines: list[_Line]) -> float:
    counts = Counter(round(line.size, 1) for line in lines)
    return float(counts.most_common(1)[0][0]) if counts else 0.0


def _modal_pitch(lines: list[_Line]) -> float:
    """The page's dominant baseline-to-baseline step, used to detect paragraph breaks."""
    steps = Counter(round(b.top - a.top) for a, b in zip(lines, lines[1:], strict=False) if b.top > a.top)
    if steps:
        return float(steps.most_common(1)[0][0])
    heights = [line.bottom - line.top for line in lines]
    return float(sum(heights) / len(heights)) if heights else 12.0


def _emit_page(
    *,
    sections: list[_Section],
    marginal_blocks: list[MarginalBlock],
    artifact_id: str,
    page_no: int,
    start_order: int,
) -> list[Block]:
    """Emit a page's blocks, each Randtitel heading placed before the section it labels.

    A Randtitel is positioned by geometry: it precedes the first section whose vertical
    span reaches its own. That is what makes the label a *heading of* the provision rather
    than a fragment inside it.
    """
    order = start_order
    blocks: list[Block] = []

    def _emit(block_type: str, text: str, level: int | None, *, marginal: bool, top: float) -> None:
        nonlocal order
        if not text:
            return
        attrs: dict[str, Any] = {"tag": "pdf", "page_no": page_no, "bbox_top": top}
        anchor = _slugify(text) if block_type == "heading" else None
        if anchor:
            attrs["anchor"] = anchor
        if marginal:
            attrs["marginal"] = True
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

    pending = sorted(marginal_blocks, key=lambda m: m.top)
    for section in sections:
        while pending and pending[0].top < section.bottom:
            marginal = pending.pop(0)
            _emit("heading", marginal.text, 3, marginal=True, top=marginal.top)
        _emit(section.type, section.text, section.level, marginal=False, top=section.top)

    # A Randtitel below the last section still belongs to the document, not the floor.
    for marginal in pending:
        _emit("heading", marginal.text, 3, marginal=True, top=marginal.top)
    return blocks


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
