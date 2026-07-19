"""Page geometry for legal PDFs: separating the marginal-heading band from the body.

Swiss ordinances set a provision's short label ("Randtitel") in a narrow band beside the
body column rather than above it. Every text-order extractor — ``pdftotext``,
``pdfplumber``'s default flow, and docling — therefore risks emitting that label *inside*
the sentence it labels, silently corrupting legal text:

    „die Führung des **Organisation** Hundeverzeichnisses"

This module answers one narrow question: **which words on a page are marginal, and which
are body?** Everything downstream (``normalize/pdf.py``) is ordinary single-column layout
once that partition is made, because subtracting the band leaves a single column behind.

### Why not x-projection gutters (ADR-0037's approach)

ADR-0037 detected columns by projecting word bounding boxes onto the x-axis and splitting
on whitespace gutters. Measured on the real Zurich ordinance AS 554.510 that signal does
not exist: the body column ends at x1 = 492.6 and the Randtitel band starts at x0 = 498.2,
a **5.6pt gutter** — narrower than ordinary inter-word spacing inside a body sentence
(p50 3.9pt, **p90 6.5pt**). No join tolerance separates them, because at p90 the gutter is
*smaller* than the gaps it would have to survive. See ADR-0041.

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

import io
import re
from collections import Counter
from collections.abc import Iterable
from dataclasses import dataclass
from typing import Any

# Two words belong to the same visual line when their vertical spans overlap by more than
# this fraction of the shorter span. Overlap (not centre distance) is what pulls a
# superscript — the Absatz number in "Art. 1 ¹ Die Aufsicht…", or a footnote marker —
# onto the body line it belongs to, while still keeping consecutive body lines apart.
_LINE_OVERLAP_RATIO = 0.5
# Words whose vertical mid-points sit within this many points share a baseline. Used only
# for the line-start histogram that finds the marginal band (see _line_start_histogram).
_BASELINE_TOLERANCE_PT = 3.0
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
class Word:
    """One extracted word with the geometry and font attributes layout needs."""

    text: str
    x0: float
    x1: float
    top: float
    bottom: float
    size: float = 0.0
    fontname: str = ""

    @property
    def height(self) -> float:
        return max(0.1, self.bottom - self.top)

    @property
    def bold(self) -> bool:
        name = self.fontname.lower()
        return "bold" in name or "black" in name or "heavy" in name


@dataclass(frozen=True)
class MarginalBlock:
    """One Randtitel: its text plus where it sits, in top-origin page coordinates."""

    page_no: int
    text: str
    top: float
    bottom: float
    side: str  # "left" | "right"


@dataclass(frozen=True)
class PageSplit:
    """A page partitioned into body words and the marginal blocks lifted out of it."""

    body_words: list[Word]
    marginal_blocks: list[MarginalBlock]


def extract_page_words(page: Any) -> list[Word]:
    """Extract a pdfplumber page's words with font size and name attached."""
    raw = page.extract_words(
        use_text_flow=False,
        keep_blank_chars=False,
        x_tolerance=1.5,
        y_tolerance=1.5,
        extra_attrs=["size", "fontname"],
    )
    words: list[Word] = []
    for item in raw:
        text = str(item.get("text", "")).strip()
        if not text:
            continue
        words.append(
            Word(
                text=text,
                x0=float(item["x0"]),
                x1=float(item["x1"]),
                top=float(item["top"]),
                bottom=float(item["bottom"]),
                size=float(item.get("size") or 0.0),
                fontname=str(item.get("fontname") or ""),
            )
        )
    return words


def group_lines(words: list[Word]) -> list[list[Word]]:
    """Group words into visual lines, ordered top-to-bottom, each left-to-right.

    Lines are formed by vertical *span overlap* against the line's tallest word so far.
    Comparing against the tallest word — rather than the line's growing bounding box —
    keeps a small superscript from stretching the line and swallowing the next one.
    """
    if not words:
        return []
    ordered = sorted(words, key=lambda w: (w.top, w.x0))
    lines: list[list[Word]] = []
    current: list[Word] = [ordered[0]]
    anchor = ordered[0]
    for word in ordered[1:]:
        overlap = min(word.bottom, anchor.bottom) - max(word.top, anchor.top)
        if overlap > _LINE_OVERLAP_RATIO * min(word.height, anchor.height):
            current.append(word)
            if word.height > anchor.height:
                anchor = word
        else:
            lines.append(current)
            current = [word]
            anchor = word
    lines.append(current)
    for line in lines:
        line.sort(key=lambda w: w.x0)
    return lines


def _line_start_histogram(words: list[Word]) -> Counter[int]:
    """Count how many visual lines begin at each x position.

    This deliberately does **not** use :func:`group_lines`. That function merges by
    vertical span overlap so a superscript joins its body line — but a Randtitel sitting
    beside a body line overlaps it just as much, so overlap-grouping would absorb the band
    into the body line and erase the very cluster this histogram exists to find. Baseline
    proximity keeps the band's lines separate, which is what the signal requires.
    """
    if not words:
        return Counter()
    ordered = sorted(words, key=lambda w: ((w.top + w.bottom) / 2.0, w.x0))
    starts: Counter[int] = Counter()
    current: list[Word] = [ordered[0]]
    centre = (ordered[0].top + ordered[0].bottom) / 2.0
    for word in ordered[1:]:
        word_centre = (word.top + word.bottom) / 2.0
        if abs(word_centre - centre) <= _BASELINE_TOLERANCE_PT:
            current.append(word)
            centre = sum((w.top + w.bottom) / 2.0 for w in current) / len(current)
        else:
            starts[round(min(w.x0 for w in current))] += 1
            current = [word]
            centre = word_centre
    starts[round(min(w.x0 for w in current))] += 1
    return starts


def split_page_words(*, words: list[Word], page_width: float, page_no: int) -> PageSplit:
    """Partition a page's words into body text and marginal-heading blocks.

    Returns every word as body when the page carries no marginal band (the common case)
    and when the guards judge the candidate band to be a genuine multi-column layout
    rather than a margin — shredding a real second column into "headings" would be a
    worse corruption than the one this module exists to prevent.
    """
    if not words or not page_width:
        return PageSplit(body_words=list(words), marginal_blocks=[])

    starts = _line_start_histogram(words)
    if not starts:
        return PageSplit(body_words=list(words), marginal_blocks=[])
    body_left = starts.most_common(1)[0][0]

    # A right-hand band is a secondary line-start cluster far right of the body edge.
    candidates = [
        x
        for x, support in starts.items()
        if x > body_left + _RIGHT_BAND_MIN_OFFSET_RATIO * page_width and support >= _MIN_BAND_LINE_SUPPORT
    ]
    right_band_x0 = float(min(candidates)) if candidates else None

    def _side(word: Word) -> str | None:
        if word.x1 < body_left - _EDGE_TOLERANCE_PT:
            return "left"
        if right_band_x0 is not None and word.x0 >= right_band_x0 - _EDGE_TOLERANCE_PT:
            return "right"
        return None

    marginal = [(side, w) for w in words if (side := _side(w)) is not None]
    if not marginal:
        return PageSplit(body_words=list(words), marginal_blocks=[])

    # Guards: a Randtitel band is narrow and text-poor. A genuine second body column is
    # neither, and must be left alone rather than shredded into "headings".
    band_words = [w for _, w in marginal]
    band_width = max(w.x1 for w in band_words) - min(w.x0 for w in band_words)
    total_mass = sum(len(w.text) for w in words)
    band_mass = sum(len(w.text) for w in band_words)
    if band_width > _MAX_BAND_WIDTH_RATIO * page_width:
        return PageSplit(body_words=list(words), marginal_blocks=[])
    if total_mass and band_mass / total_mass > _MAX_BAND_MASS_RATIO:
        return PageSplit(body_words=list(words), marginal_blocks=[])

    band = {id(w) for w in band_words}
    body_words = [w for w in words if id(w) not in band]
    return PageSplit(
        body_words=body_words,
        marginal_blocks=_group_blocks(marginal, page_no=page_no),
    )


def detect_marginal_blocks(pdf_bytes: bytes) -> list[MarginalBlock]:
    """Return every marginal-heading block in the document, in reading order."""
    import pdfplumber

    blocks: list[MarginalBlock] = []
    with pdfplumber.open(io.BytesIO(pdf_bytes)) as pdf:
        for index, page in enumerate(pdf.pages):
            words = extract_page_words(page)
            if not words:
                continue
            split = split_page_words(
                words=words,
                page_width=float(page.width or 0.0),
                page_no=index + 1,
            )
            blocks.extend(split.marginal_blocks)
    return blocks


def _group_blocks(marginal: list[tuple[str, Word]], *, page_no: int) -> list[MarginalBlock]:
    """Coalesce band words into blocks separated by vertical whitespace."""
    ordered = sorted(marginal, key=lambda pair: (pair[1].top, pair[1].x0))
    groups: list[list[tuple[str, Word]]] = []
    current: list[tuple[str, Word]] = []
    for side, word in ordered:
        if current and word.top - max(w.bottom for _, w in current) > _BLOCK_GAP_PT:
            groups.append(current)
            current = []
        current.append((side, word))
    if current:
        groups.append(current)

    blocks: list[MarginalBlock] = []
    for group in groups:
        lines = group_lines([w for _, w in group])
        text = join_wrapped_lines(" ".join(w.text for w in line) for line in lines)
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


# A wrap hyphen may be extracted as part of the word ("Hundehaltungsvoraus-") or as a
# detached token ("ob -"), depending on the PDF's character spacing. Both are the same
# typographic event and both must heal, or the joined word stays unsearchable.
_SOFT_HYPHEN_RE = re.compile(r"(\w)\s*[-­]$")
# German sets an elided compound as "Halter- und Hundedaten". When such an ellipsis falls
# at a line end the trailing hyphen must be kept, not healed away into "Halterund".
_ELLIPSIS_CONTINUATIONS = {"und", "oder", "bzw", "sowie", "beziehungsweise"}


def join_wrapped_lines(lines: Iterable[str]) -> str:
    """Join lines, healing words hyphenated across the line break.

    Legal PDFs hyphenate aggressively — "Hundehaltungsvoraus-" / "setzungen". Unless the
    two halves rejoin, a search for ``Hundehaltungsvoraussetzungen`` cannot match the text
    at all, which is silent corruption of the same class as the marginal splice (#643).

    Only a hyphen following a word character and preceding a lower-case continuation is
    healed, and never when that continuation is a conjunction — so a genuine elided
    compound ("Halter- und Hundedaten") keeps its hyphen.
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
        first_word = line.split(" ", 1)[0].strip(".,;:").lower()
        if match and line[:1].islower() and first_word not in _ELLIPSIS_CONTINUATIONS:
            out = out[: match.start(1) + 1] + line
        else:
            out = f"{out} {line}"
    return " ".join(out.split())
