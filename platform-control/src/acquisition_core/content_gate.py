"""Shared legal-text acceptance gate for acquisition providers.

Providers that scrape HTML portals can silently capture a *navigation
shell* — a JavaScript SPA's menu chrome — in place of the statute they
were pointed at. Such a page is a 200, has visible text, and indexes
fine, so nothing downstream objects: it is the "demo that lies
convincingly" failure ADR-0033 exists to prevent, one layer earlier
(the acquisition layer) than the ADR was looking. See #631.

The `scripts/ch-fedlex-fast-loop.sh` canary already caught this with a
generic heuristic (`art_density = 0 < 3`), but that check was
Fedlex-hardcoded and ran only in a canary script, not in the acquisition
path every provider shares. This module lifts that heuristic into a
shared, jurisdiction-agnostic gate so "acceptance evidence" means the
same thing everywhere: a captured document must actually look like law.

The signal is deliberately cheap and content-only (no rendering): count
legal-text markers (`Art.`, `§`, `Abs.`, Italian `comma`/`art.`, …) in
the *visible* text, and measure the script/style-to-text ratio as
corroborating diagnostic evidence. A real statute page clears the marker
threshold comfortably; a JS navigation shell scores zero.
"""

from __future__ import annotations

import re
from dataclasses import dataclass

# Occurrences of these markers across all raw artifacts are what the Fedlex
# canary counted (`art_density >= 3`). Generalised here to the marker
# vocabularies of the jurisdictions the portal providers cover: DE/CH German
# (`Art.`, `Artikel`, `§`, `Abs.`, `Ziff.`), and IT Italian (`art.`, `comma`,
# `lett.`). Matching is case-insensitive; word boundaries keep `comma`/`lit`
# from matching inside unrelated words.
_LEGAL_MARKER_RE = re.compile(
    r"art\.|artikel|§|abs\.|ziff\.|\bcomma\b|\blett\.|\blit\.",
    re.IGNORECASE,
)

# `<script>`/`<style>` blocks (and their content) are chrome, not legal text.
# Captured to both strip them from the visible text and measure their bulk.
_SCRIPT_STYLE_RE = re.compile(
    r"<(script|style)\b[^>]*>.*?</\1>",
    re.IGNORECASE | re.DOTALL,
)
_TAG_RE = re.compile(r"<[^>]+>")
_WHITESPACE_RE = re.compile(r"\s+")

# The Fedlex canary's threshold: at least 3 legal-text markers. A statute page
# clears this comfortably; a navigation shell scores 0.
DEFAULT_MIN_LEGAL_MARKERS = 3

# Content types whose body is text we can assess. Anything else (e.g. a binary
# artifact) cannot be inspected this way, so the gate abstains rather than
# guessing — the provider's own carriability checks own that case.
_ASSESSABLE_CONTENT_TYPES = frozenset(
    {"text/html", "application/xhtml+xml", "application/xml", "text/xml"}
)


@dataclass(frozen=True, slots=True)
class LegalTextAssessment:
    """Verdict of the legal-text density gate for one captured body."""

    is_legal_text: bool
    marker_count: int
    visible_text_length: int
    script_style_length: int
    script_to_text_ratio: float
    min_markers: int
    reason: str | None

    def as_evidence(self) -> dict[str, float | int]:
        """Compact, JSON-safe diagnostics for run/response payloads."""
        return {
            "legal_marker_count": self.marker_count,
            "visible_text_length": self.visible_text_length,
            "script_style_length": self.script_style_length,
            "script_to_text_ratio": round(self.script_to_text_ratio, 2),
            "min_legal_markers": self.min_markers,
        }


def _visible_text(body_text: str) -> str:
    """Strip script/style blocks and tags, returning collapsed visible text."""
    without_scripts = _SCRIPT_STYLE_RE.sub(" ", body_text)
    without_tags = _TAG_RE.sub(" ", without_scripts)
    return _WHITESPACE_RE.sub(" ", without_tags).strip()


def assess_legal_text_density(
    body_text: str,
    *,
    content_type: str | None = None,
    min_markers: int = DEFAULT_MIN_LEGAL_MARKERS,
) -> LegalTextAssessment:
    """Assess whether a captured body looks like legal text rather than chrome.

    The document passes when its visible text carries at least ``min_markers``
    legal-text markers. The script/style-to-text ratio is reported as
    corroborating evidence (a JS shell is script-heavy and marker-poor) but is
    not itself fail-closed, so a legitimately script-heavy statute page that
    still carries the markers is not penalised.

    ``content_type`` is honoured so the gate abstains (``is_legal_text=True``,
    marker check skipped) on bodies it cannot meaningfully inspect; the
    provider's own content-type handling owns those.
    """
    if content_type is not None:
        normalized = content_type.split(";", 1)[0].strip().lower()
        if normalized and normalized not in _ASSESSABLE_CONTENT_TYPES:
            return LegalTextAssessment(
                is_legal_text=True,
                marker_count=0,
                visible_text_length=0,
                script_style_length=0,
                script_to_text_ratio=0.0,
                min_markers=min_markers,
                reason=None,
            )

    visible = _visible_text(body_text)
    marker_count = len(_LEGAL_MARKER_RE.findall(visible))
    script_style_length = sum(len(match.group(0)) for match in _SCRIPT_STYLE_RE.finditer(body_text))
    ratio = script_style_length / max(len(visible), 1)

    is_legal_text = marker_count >= min_markers
    reason: str | None = None
    if not is_legal_text:
        reason = (
            f"captured document has {marker_count} legal-text marker(s) "
            f"(Art./§/Abs./comma), below the acceptance threshold of "
            f"{min_markers}; {len(visible)} chars of visible text vs "
            f"{script_style_length} chars of script/style "
            f"(script-to-text ratio {ratio:.1f}). This looks like a navigation "
            "or JavaScript shell, not legal text — refusing rather than "
            "capturing it as acceptance evidence (see #631)."
        )

    return LegalTextAssessment(
        is_legal_text=is_legal_text,
        marker_count=marker_count,
        visible_text_length=len(visible),
        script_style_length=script_style_length,
        script_to_text_ratio=ratio,
        min_markers=min_markers,
        reason=reason,
    )
