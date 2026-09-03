"""The text-level law assertion: does the extracted text support the claim "this is law"?

ADR-0047's invariant, applied to one manifestation:

    The canonical corpus contains only documents whose class has an implemented
    handler. Nothing reaches canonical by fallback, by default, or by producing an
    empty artifact that satisfies a structural check.

**Why this module has to exist at all.** Acquisition already runs two gates, and both
of them stop short of this one by construction:

- ``acquisition_core.artifact_guard`` judges the *bytes as received* — declared content
  type, format magic number, a byte floor. Its own docstring scopes it honestly: it
  "defeats #716 and nothing more". A 84 KB scanned ordinance with no text layer clears
  its byte floor comfortably.
- ``acquisition_core.content_gate.assess_legal_text_density`` judges *visible text* by
  counting legal-text markers — but its ``_ASSESSABLE_CONTENT_TYPES`` is HTML/XML only,
  so it **abstains on every PDF**. ``lexfind_api_provider`` calls it with an empty string
  and records ``legal_text_assessment: abstained_binary_manifestation`` precisely so the
  abstention is in the evidence rather than implied by its absence.

So a structurally valid PDF whose text is a cover sheet, a consent interstitial, or
nothing at all passes acquisition end to end. Judging it needs extraction, and
extraction lives here (ADR-0041). That is the gap this module closes, and it is the one
both ADR-0047 §Context and ``artifact_guard``'s docstring hand to document-intelligence
by name.

**What "not law" looks like, and the two floors that catch it.**

- A **character floor**: text that is too short to be a legal instrument at all. The byte
  floor upstream cannot see this — an image-only PDF is large and extracts to nothing.
- A **legal-marker floor**: text of adequate length that carries none of the structural
  markers every Swiss legal text carries (``Art.``, ``§``, ``Abs.``, ``comma``, ``cpv.``,
  ``alinéa``). A title page, an error page or a consent interstitial scores zero.

Both floors are configurable (``DI_QUARANTINE_MIN_EXTRACTED_CHARS`` /
``DI_QUARANTINE_MIN_LEGAL_MARKERS``, overridable per bundle through ``di_overrides``),
because ADR-0047 is explicit that over-quarantine stalls ingestion and that "the honest
minimum for a cantonal act is not the honest minimum for a one-article communal
ordinance".

**Marker vocabulary drift.** ADR-0047 §Context: the vocabulary and threshold "should be
reused from ``content_gate``, not reimplemented — the two must not drift into separate
opinions about what law looks like". document-intelligence and platform-control are
separate distributions (separate ``pyproject.toml``, separate containers), so there is no
import to share. The vocabulary below is therefore a documented **superset** of
``content_gate``'s, and ``tests/test_quarantine.py`` fails if platform-control grows a
marker this module does not have. Superset, not equal, because the acquisition gate only
ever meets HTML from portals whose vocabulary is DE/IT, while this gate meets the whole
of LexFind — 26 cantons plus Bund, so DE/FR/IT.

**Which modalities the legal-text floors apply to.** Exactly the complement of
``content_gate._ASSESSABLE_CONTENT_TYPES`` — every content type acquisition's gate
abstained on. Today that is ``application/pdf`` (the case ADR-0047 names) and the other
non-HTML/XML modalities the pipeline can normalise. HTML and XML were already judged by
``content_gate`` at capture, so re-judging them here would be a second opinion on a
settled question rather than a gate on an unguarded one; ``tests/test_quarantine.py``
fails if the upstream set changes, because either direction of drift opens a hole — a
modality judged twice, or one judged by nobody.

Two structural checks — ``no_text_layer`` and ``no_sections_extracted`` — run on **every**
modality, because nothing upstream performs them at all.

Known residual gap, stated rather than papered over: ``content_gate`` is wired into
``portal_http_provider_base`` only, so an HTML capture from a provider that is not a
portal HTTP provider is marker-checked by neither gate. Closing that belongs in
platform-control, not here.
"""

from __future__ import annotations

import re
from collections.abc import Mapping
from dataclasses import dataclass
from typing import Any

from document_intelligence.normalize.ir import NormalizedDocumentIR

__all__ = [
    "DEFAULT_MIN_EXTRACTED_CHARS",
    "DEFAULT_MIN_LEGAL_MARKERS",
    "LEGAL_MARKER_PATTERN",
    "QUARANTINE_REASONS",
    "QuarantineThresholds",
    "QuarantineVerdict",
    "UPSTREAM_ASSESSED_CONTENT_TYPES",
    "assess_quarantine",
    "count_legal_markers",
]


# ADR-0047 §3: the taxonomy is closed. A free-text reason degrades into prose nobody
# groups by, and "miscellaneous" becomes the largest bucket. A new reason requires an
# entry here *and* a row in the ADR's table saying which of the two exits it takes.
#
#   no_text_layer            — class 2 — exit: implement (OCR)
#   below_content_floor      — class 2/3 — exit: fix or implement
#   no_sections_extracted    — class 3 — exit: fix
#   unsupported_manifestation — exit: implement
#   format_signature_mismatch — class 1 — exit: fix (should not have reached DI)
QUARANTINE_REASONS = frozenset(
    {
        "no_text_layer",
        "below_content_floor",
        "no_sections_extracted",
        "unsupported_manifestation",
        "format_signature_mismatch",
    }
)

# A documented superset of `acquisition_core.content_gate._LEGAL_MARKER_RE`. The shared
# half must stay character-identical — the drift test compares alternative by
# alternative — and the DI-only half covers the French and Italian equivalents of `Abs.`
# that a cantonal corpus needs and a DE/IT portal gate never met.
#
# Deliberately *not* included: bare `al.` (French "alinéa") and `ch.` ("chiffre"). Both
# match inside ordinary prose ("et al.", "ch." as an abbreviation) and would let a cover
# page clear a floor of three markers on abbreviations alone — a gate that passes
# everything is worse than no gate, because it looks like one that works.
LEGAL_MARKER_PATTERN = (
    # ── shared with acquisition_core.content_gate ──
    r"art\.|artikel|§|abs\.|ziff\.|\bcomma\b|\blett\.|\blit\."
    # ── FR/IT equivalents of `Abs.`, for the cantonal corpus (#731) ──
    r"|\balinéa\b|cpv\.|\bcapoverso\b|\blet\."
)
_LEGAL_MARKER_RE = re.compile(LEGAL_MARKER_PATTERN, re.IGNORECASE)

# Mirrors `acquisition_core.content_gate._ASSESSABLE_CONTENT_TYPES`. These are the
# manifestations acquisition's gate *did* judge; everything else it abstained on, and
# the abstention is what the legal-text floors below exist to cover. Kept equal to the
# upstream set by the drift test, so the two gates partition the modality space between
# them instead of overlapping or leaving a hole.
UPSTREAM_ASSESSED_CONTENT_TYPES = frozenset({"text/html", "application/xhtml+xml", "application/xml", "text/xml"})

# `content_gate.DEFAULT_MIN_LEGAL_MARKERS`, and before that the Fedlex canary's
# `art_density >= 3`. A statute clears it on its first page; a navigation shell, a cover
# sheet or a consent interstitial scores zero.
DEFAULT_MIN_LEGAL_MARKERS = 3

# Measured, not guessed. The ZH Hundeverordnung (AS 554.510, `tests/fixtures/`) — the
# cantonal rung of ADR-0033's dog question and among the shorter real acts — normalises
# to 3 080 characters of body text. A one-article communal ordinance is an order of
# magnitude shorter than that, so the floor sits an order of magnitude below it again:
# low enough that genuine short law is never refused, high enough that an image-only PDF
# (0 characters) and a cover sheet cannot pass.
DEFAULT_MIN_EXTRACTED_CHARS = 200

# Keys read from the bundle manifest's `di_overrides`. ADR-0047: "Floors are therefore
# per-source config, not global constants."
_OVERRIDE_MIN_CHARS = "quarantine_min_extracted_chars"
_OVERRIDE_MIN_MARKERS = "quarantine_min_legal_markers"


@dataclass(frozen=True, slots=True)
class QuarantineThresholds:
    """The two text-level floors, resolved for one bundle."""

    min_extracted_chars: int = DEFAULT_MIN_EXTRACTED_CHARS
    min_legal_markers: int = DEFAULT_MIN_LEGAL_MARKERS

    def with_overrides(self, di_overrides: Mapping[str, Any] | None) -> QuarantineThresholds:
        """Apply a bundle's per-source floors, ignoring anything not a non-negative int.

        A malformed override must not silently *lower* a floor, so anything that does not
        parse as a non-negative integer leaves the configured default in place.
        """
        if not di_overrides:
            return self
        return QuarantineThresholds(
            min_extracted_chars=_coerce_floor(di_overrides.get(_OVERRIDE_MIN_CHARS), self.min_extracted_chars),
            min_legal_markers=_coerce_floor(di_overrides.get(_OVERRIDE_MIN_MARKERS), self.min_legal_markers),
        )


@dataclass(frozen=True, slots=True)
class QuarantineVerdict:
    """Outcome of the text-level assertion for one manifestation.

    ``reason`` is a slug from :data:`QUARANTINE_REASONS`, never prose — it is what an
    operator groups the queue by, and what decides which of ADR-0047's two exits the
    document takes. ``detail`` carries the human sentence; the counters carry the
    evidence that produced the verdict.
    """

    quarantined: bool
    reason: str | None = None
    detail: str | None = None
    extracted_chars: int = 0
    min_extracted_chars: int = 0
    legal_marker_count: int = 0
    min_legal_markers: int = 0

    def as_record(self) -> dict[str, Any]:
        """The block written to the processing manifest's ``quarantine`` column.

        Fixed keys with fixed types on purpose: a free-form evidence map produces a
        different struct per row, and the published surfaces are columnar.
        """
        return {
            "reason": self.reason or "",
            "detail": self.detail or "",
            "extracted_chars": self.extracted_chars,
            "min_extracted_chars": self.min_extracted_chars,
            "legal_marker_count": self.legal_marker_count,
            "min_legal_markers": self.min_legal_markers,
        }


def count_legal_markers(text: str) -> int:
    """Number of legal-text markers (``Art.``/``§``/``Abs.``/``comma``/…) in ``text``."""
    return len(_LEGAL_MARKER_RE.findall(text))


def assess_quarantine(
    *,
    normalized_document: NormalizedDocumentIR,
    content_type: str | None,
    thresholds: QuarantineThresholds | None = None,
) -> QuarantineVerdict:
    """Decide whether a normalised manifestation may become a canonical document.

    Check order is deliberate and mirrors ``artifact_guard.check_capture``: the most
    specific cause runs first, so the recorded reason names the actual defect rather than
    a downstream symptom. An image-only PDF must report ``no_text_layer`` — the class we
    have not implemented, whose exit is OCR — not ``below_content_floor``, which reads as
    a threshold that could simply be lowered.
    """
    effective = thresholds or QuarantineThresholds()
    text = normalized_document.full_text
    marker_count = count_legal_markers(text)

    def verdict(quarantined: bool, reason: str | None = None, detail: str | None = None) -> QuarantineVerdict:
        return QuarantineVerdict(
            quarantined=quarantined,
            reason=reason,
            detail=detail,
            extracted_chars=len(text),
            min_extracted_chars=effective.min_extracted_chars,
            legal_marker_count=marker_count,
            min_legal_markers=effective.min_legal_markers,
        )

    # Class 2 (ADR-0047): a scanned or image-only PDF. The normaliser already knows —
    # `normalize/pdf.py` sets this flag and then *continues*, emitting an empty IR that
    # every structural check downstream accepts. This is the line that stops it.
    if normalized_document.metadata.get("pdf_no_text_layer") is True:
        return verdict(
            True,
            "no_text_layer",
            "the PDF carries no text layer, so nothing was extracted; it needs OCR, "
            "which is not implemented — admitting it would publish a document the "
            "corpus holds no text for",
        )

    # Class 3: the handler ran and produced nothing. Distinct from `no_text_layer`
    # because the exit differs — this is a defect in our logic, not a missing class.
    if not normalized_document.blocks or not text.strip():
        return verdict(
            True,
            "no_sections_extracted",
            "normalisation produced no blocks, so the document would be published empty",
        )

    # The legal-text floors. Applied to the manifestations `content_gate` abstained on;
    # see the module docstring for why re-judging text modalities here would be a second
    # opinion rather than a gate.
    if _assessed_upstream(content_type):
        return verdict(False)

    if len(text) < effective.min_extracted_chars:
        return verdict(
            True,
            "below_content_floor",
            f"{len(text)} characters of extracted text, floor is {effective.min_extracted_chars}; "
            "too short to be the legal instrument this manifestation claims to be",
        )

    if marker_count < effective.min_legal_markers:
        return verdict(
            True,
            "below_content_floor",
            f"{marker_count} legal-text marker(s) (Art./§/Abs./comma/cpv.) in "
            f"{len(text)} characters, floor is {effective.min_legal_markers}; the text "
            "extracted fine but does not read as law — a cover page, an error page or a "
            "consent interstitial rather than the statute",
        )

    return verdict(False)


def _assessed_upstream(content_type: str | None) -> bool:
    if not content_type:
        return False
    return content_type.split(";", 1)[0].strip().lower() in UPSTREAM_ASSESSED_CONTENT_TYPES


def _coerce_floor(value: Any, fallback: int) -> int:
    if isinstance(value, bool) or not isinstance(value, int):
        return fallback
    return value if value >= 0 else fallback
