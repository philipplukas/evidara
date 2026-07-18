"""Geometric detection of marginal headings ("Randtitel") in legal PDFs.

Swiss ordinances set a provision's short label in a narrow band beside the body column
rather than above it. Every text-order extractor — ``pdftotext``, ``pdfplumber``'s default
flow, and (partially) docling — therefore risks emitting that label *inside* the sentence
it labels, silently corrupting legal text.

This module answers one narrow question: **which words on a page are marginal?** It does
not extract reading order (docling does that, see ``ingest/docling_adapter.py``); it only
supplies the geometry that lets a post-pass lift a Randtitel out of the paragraph docling
appended it to. Keeping the two concerns apart is deliberate — the extractor may change
again, the page geometry will not.

### Why not x-projection gutters (ADR-0037's approach)

ADR-0037 detected columns by projecting word bounding boxes onto the x-axis and splitting
on whitespace gutters. Measured on the real Zurich ordinance AS 554.510 that signal does
not exist: the body column ends at x1 = 492.6 and the Randtitel band starts at x0 = 498.2,
a **5.6pt gutter** — narrower than ordinary inter-word spacing inside a body sentence
(p50 3.9pt, **p90 6.5pt**). No join tolerance separates them, because at p90 the gutter is
*smaller* than the gaps it would have to survive. See ADR-0038.

### The signal that does work: shared left edges

Body text is set flush to a single left margin, so **line-start x-positions cluster hard**
at the body's left edge (measured: 34 of 50 lines on page 1 start at x = 103). A marginal
band is a second, much smaller cluster of line starts far from that edge (5 lines at
x = 498). Justified body text scatters its *word* x0 values but never its *line-start*
values, which is exactly why line starts separate the bands where word projection cannot.

The band may sit on either side: the ordinance is set as a booklet, so recto pages carry
the Randtitel on the **right** (page 1: x 498.2–571.8) and verso pages on the **left**
(page 2: x 17.7–94.7). ADR-0037's normaliser only ever looked left, which is a second,
independent reason it could not have worked on this document.
"""

from __future__ import annotations

import re
from collections import Counter
from dataclasses import dataclass, replace
from typing import Any

from document_intelligence.normalize.ir import Block, NormalizedDocumentIR

# Words whose vertical mid-points sit within this many points belong to one visual line.
_LINE_TOLERANCE_PT = 3.0
# A marginal band must start at least this fraction of the page width right of the body
# edge, so an indented body line (a list item, a quotation) is never mistaken for a band.
_RIGHT_BAND_MIN_OFFSET_RATIO = 0.4
# How many lines must share a left edge before it counts as a band rather than an outlier.
_MIN_BAND_LINE_SUPPORT = 2
# Guards against mistaking a genuine two-column body for a marginal band. A Randtitel band
# is narrow and carries little text; a real second column is neither.
_MAX_BAND_WIDTH_RATIO = 0.35
_MAX_BAND_MASS_RATIO = 0.25
# Vertical gap (pt) that separates two distinct marginal blocks.
_BLOCK_GAP_PT = 6.0
# Tolerance when comparing a word's edge to a detected band edge.
_EDGE_TOLERANCE_PT = 2.0


@dataclass(frozen=True)
class MarginalBlock:
    """One Randtitel: its text plus where it sits, in top-origin page coordinates."""

    page_no: int
    text: str
    top: float
    bottom: float
    side: str  # "left" | "right"


@dataclass(frozen=True)
class _Word:
    text: str
    x0: float
    x1: float
    top: float
    bottom: float

    @property
    def cy(self) -> float:
        return (self.top + self.bottom) / 2.0


def detect_marginal_blocks(pdf_bytes: bytes) -> list[MarginalBlock]:
    """Return every marginal-heading block in the document, in reading order.

    Returns an empty list for documents with no marginal band (the common case) and for
    anything the guards judge to be a genuine multi-column layout rather than a margin.
    """
    import io

    import pdfplumber

    blocks: list[MarginalBlock] = []
    with pdfplumber.open(io.BytesIO(pdf_bytes)) as pdf:
        for index, page in enumerate(pdf.pages):
            words = _extract_words(page)
            if not words:
                continue
            blocks.extend(
                _blocks_for_page(
                    words=words,
                    page_width=float(page.width or 0.0),
                    page_no=index + 1,
                )
            )
    return blocks


def _blocks_for_page(*, words: list[_Word], page_width: float, page_no: int) -> list[MarginalBlock]:
    lines = _group_lines(words)
    if not lines or not page_width:
        return []

    starts = Counter(round(min(w.x0 for w in line)) for line in lines)
    body_left = starts.most_common(1)[0][0]

    # A right-hand band is a secondary line-start cluster far right of the body edge.
    right_band_x0: float | None = None
    candidates = [
        x
        for x, support in starts.items()
        if x > body_left + _RIGHT_BAND_MIN_OFFSET_RATIO * page_width and support >= _MIN_BAND_LINE_SUPPORT
    ]
    if candidates:
        right_band_x0 = float(min(candidates))

    def _is_marginal(word: _Word) -> str | None:
        if word.x1 < body_left - _EDGE_TOLERANCE_PT:
            return "left"
        if right_band_x0 is not None and word.x0 >= right_band_x0 - _EDGE_TOLERANCE_PT:
            return "right"
        return None

    marginal = [(side, w) for w in words if (side := _is_marginal(w)) is not None]
    if not marginal:
        return []

    # Guards: a Randtitel band is narrow and text-poor. A genuine second body column is
    # neither, and must be left alone rather than shredded into "headings".
    band_words = [w for _, w in marginal]
    band_width = max(w.x1 for w in band_words) - min(w.x0 for w in band_words)
    total_mass = sum(len(w.text) for w in words)
    band_mass = sum(len(w.text) for w in band_words)
    if band_width > _MAX_BAND_WIDTH_RATIO * page_width:
        return []
    if total_mass and band_mass / total_mass > _MAX_BAND_MASS_RATIO:
        return []

    return _group_blocks(marginal, page_no=page_no)


def _group_blocks(marginal: list[tuple[str, _Word]], *, page_no: int) -> list[MarginalBlock]:
    """Coalesce band words into blocks separated by vertical whitespace."""
    ordered = sorted(marginal, key=lambda pair: (pair[1].top, pair[1].x0))
    groups: list[list[tuple[str, _Word]]] = []
    current: list[tuple[str, _Word]] = []
    for side, word in ordered:
        if current and word.top - max(w.bottom for _, w in current) > _BLOCK_GAP_PT:
            groups.append(current)
            current = []
        current.append((side, word))
    if current:
        groups.append(current)

    blocks: list[MarginalBlock] = []
    for group in groups:
        lines = _group_lines([w for _, w in group])
        text = _join_wrapped_lines(" ".join(w.text for w in sorted(line, key=lambda w: w.x0)) for line in lines)
        if not text:
            continue
        blocks.append(
            MarginalBlock(
                page_no=page_no,
                text=text,
                top=min(w.top for _, w in group),
                bottom=max(w.bottom for _, w in group),
                side=group[0][0],
            )
        )
    return blocks


_SOFT_HYPHEN_RE = re.compile(r"(\w)[-­]$")


def _join_wrapped_lines(lines: Any) -> str:
    """Join a block's lines, healing words hyphenated across the line break.

    A narrow margin band wraps aggressively, so "Aufhebung bis-" / "herigen Rechts" must
    rejoin as "Aufhebung bisherigen Rechts" — otherwise the lifted heading will not match
    the text the extractor produced. Only a hyphen following a word character and preceding
    a lower-case continuation is healed, so a genuine compound ("Halter- und Hundedaten")
    keeps its hyphen.
    """
    out = ""
    for line in lines:
        line = " ".join(line.split())
        if not line:
            continue
        if not out:
            out = line
            continue
        match = _SOFT_HYPHEN_RE.search(out)
        if match and line[:1].islower():
            out = out[: match.start(1) + 1] + line
        else:
            out = f"{out} {line}"
    return " ".join(out.split())


def _group_lines(words: list[_Word]) -> list[list[_Word]]:
    if not words:
        return []
    ordered = sorted(words, key=lambda w: (w.cy, w.x0))
    lines: list[list[_Word]] = []
    current: list[_Word] = [ordered[0]]
    running_cy = ordered[0].cy
    for word in ordered[1:]:
        if abs(word.cy - running_cy) <= _LINE_TOLERANCE_PT:
            current.append(word)
            running_cy = sum(w.cy for w in current) / len(current)
        else:
            lines.append(current)
            current = [word]
            running_cy = word.cy
    lines.append(current)
    return lines


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


def lift_marginal_headings(
    ir: NormalizedDocumentIR,
    marginal_blocks: list[MarginalBlock],
) -> tuple[NormalizedDocumentIR, dict[str, Any]]:
    """Lift each detected Randtitel out of the paragraph an extractor merged it into.

    Docling preserves the *sentence* (it never interleaves the label mid-clause the way a
    top-to-bottom dump does) but it appends the label to the end of the paragraph it sits
    beside — "…Sache des Sicherheitsdepartements. Organisation". Sometimes it emits the
    label as a standalone text item instead, but at the wrong point in reading order
    (page 2's Randtitel all land after the last article).

    Both cases are repaired the same way, and geometry decides every step:

    1. A candidate IR block must sit on the **same page** and its vertical span must
       overlap the Randtitel's. Nothing else is eligible, so a phrase that merely happens
       to recur elsewhere in the document can never be stripped.
    2. Among candidates, an **exact** text match wins (docling emitted the label on its
       own), then a **suffix** match (docling appended it), then a **containment** match.
    3. The label is removed from the body text and re-emitted as its own heading block,
       positioned immediately before the block it labels.

    A Randtitel that matches nothing is left alone rather than invented into the output —
    if the extractor already handled it, or dropped it, that is not this pass's business
    to guess about.
    """
    blocks = list(ir.blocks)
    lifted = 0
    unmatched: list[str] = []

    for marginal in marginal_blocks:
        target = _match_marginal(blocks, marginal)
        if target is None:
            unmatched.append(marginal.text)
            continue
        index, remainder, was_exact = target
        heading = _as_heading(blocks[index], marginal.text)
        if was_exact:
            blocks.pop(index)
            insert_at = _reading_order_slot(blocks, marginal, fallback=index)
        else:
            blocks[index] = replace(blocks[index], text=remainder)
            insert_at = index
        blocks.insert(insert_at, heading)
        lifted += 1

    renumbered = [replace(block, order=order) for order, block in enumerate(blocks)]
    diagnostics: dict[str, Any] = {
        "detected": len(marginal_blocks),
        "lifted": lifted,
        "unmatched": unmatched,
    }
    return NormalizedDocumentIR(blocks=renumbered, metadata=dict(ir.metadata)), diagnostics


def _match_marginal(
    blocks: list[Block],
    marginal: MarginalBlock,
) -> tuple[int, str, bool] | None:
    """Find the block carrying this Randtitel: (index, text without it, was_exact)."""
    needle = " ".join(marginal.text.split())
    if not needle:
        return None

    candidates = [i for i, block in enumerate(blocks) if _overlaps(block, marginal)]
    for index in candidates:
        if " ".join(blocks[index].text.split()) == needle:
            return index, "", True
    for index in candidates:
        collapsed = " ".join(blocks[index].text.split())
        if collapsed.endswith(needle):
            return index, collapsed[: -len(needle)].strip(), False
    for index in candidates:
        collapsed = " ".join(blocks[index].text.split())
        if needle in collapsed:
            return index, " ".join(collapsed.replace(needle, " ", 1).split()), False
    return None


def _overlaps(block: Block, marginal: MarginalBlock) -> bool:
    attrs = block.attrs or {}
    if attrs.get("page_no") != marginal.page_no:
        return False
    top, bottom = attrs.get("bbox_top"), attrs.get("bbox_bottom")
    if top is None or bottom is None:
        return False
    return float(top) - _LINE_TOLERANCE_PT <= marginal.bottom and float(bottom) + _LINE_TOLERANCE_PT >= marginal.top


def _reading_order_slot(blocks: list[Block], marginal: MarginalBlock, *, fallback: int) -> int:
    """Where a standalone Randtitel belongs: before the first block it could label."""
    for index, block in enumerate(blocks):
        attrs = block.attrs or {}
        if attrs.get("page_no") != marginal.page_no:
            continue
        bottom = attrs.get("bbox_bottom")
        if bottom is not None and float(bottom) + _LINE_TOLERANCE_PT >= marginal.top:
            return index
    return min(fallback, len(blocks))


def _as_heading(neighbour: Block, text: str) -> Block:
    attrs = dict(neighbour.attrs or {})
    attrs["marginal"] = True
    anchor = _slugify(text)
    if anchor:
        attrs["anchor"] = anchor
    return replace(
        neighbour,
        id=f"{neighbour.id}_randtitel",
        type="heading",
        text=text,
        level=3,
        attrs=attrs,
    )


_SLUG_RE = re.compile(r"[^a-z0-9]+")


def _slugify(value: str) -> str | None:
    slug = _SLUG_RE.sub("_", value.strip().lower()).strip("_")
    return slug or None
