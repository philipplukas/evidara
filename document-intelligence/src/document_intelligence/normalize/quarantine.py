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

Both floors are configurable through ``DI_QUARANTINE_MIN_EXTRACTED_CHARS`` /
``DI_QUARANTINE_MIN_LEGAL_MARKERS``, because ADR-0047 is explicit that over-quarantine
stalls ingestion and that "the honest minimum for a cantonal act is not the honest minimum
for a one-article communal ordinance".

**The per-source lever ADR-0047 asks for is only half-built, and the half that is missing
is the other end.** This module reads ``di_overrides.quarantine_min_extracted_chars`` /
``quarantine_min_legal_markers`` off the bundle manifest, and the contract schema declares
them — but **nothing in platform-control emits ``di_overrides`` at all** (the key appears
nowhere under ``platform-control/src``; ``events/artifact_bundle.py`` never sets it). So
the only lever that works today is the environment variable, which moves the floor for
every source at once. Do not read the ``di_overrides`` support here as a live per-source
control: it is the receiving half of a wire whose sending half does not exist yet.

**Marker vocabulary drift.** ADR-0047 §Context: the vocabulary and threshold "should be
reused from ``content_gate``, not reimplemented — the two must not drift into separate
opinions about what law looks like". document-intelligence and platform-control are
separate distributions (separate ``pyproject.toml``, separate containers), so there is no
import to share. The vocabulary below is therefore a documented **superset** of
``content_gate``'s, and ``tests/test_quarantine.py`` fails if platform-control grows a
marker this module does not have. Superset, not equal, because the acquisition gate only
ever meets HTML from portals whose vocabulary is DE/IT, while this gate meets the whole
of LexFind — 26 cantons plus Bund, so DE/FR/IT.

The *threshold* deliberately differs from upstream's, on measured evidence; see
:data:`DEFAULT_MIN_LEGAL_MARKERS`. The relation the drift test pins is that this gate is
never **stricter** than acquisition — a DI floor above `content_gate`'s would withhold a
document acquisition had already accepted as law.

**Which modalities the legal-text floors apply to.** Exactly the complement of
``content_gate._ASSESSABLE_CONTENT_TYPES`` — every content type acquisition's gate
*could* assess. Today that is ``application/pdf`` (the case ADR-0047 names) and the other
non-HTML/XML modalities the pipeline can normalise. HTML and XML are skipped here on the
theory that ``content_gate`` judged them at capture.

**That theory is only true for three providers, and this is the biggest hole left.**
``assess_legal_text_density`` has exactly two call sites: ``portal_http_provider_base.py``
(so every provider that *inherits* it) and ``lexfind_api_provider.py``, which is the
deliberate abstain. Only ``CantonHttpProvider``, ``BundeslandHttpProvider`` and
``RegioneHttpProvider`` extend that base. ``GemeindeHttpProvider`` (the municipal rung),
``FedlexSparqlProvider`` (the federal rung), ``RisOgdProvider``, ``LegifranceProvider``,
``EurLexSparqlProvider``, ``ChCourtDecisionsProvider``, ``DeterministicHttpProvider``,
``FirecrawlProvider`` and ``CassetteProvider`` are all plain classes. So HTML/XML from ~10
of 13 providers is marker-checked by **neither** gate, and ``normalize/html.py``'s
tag-stripping fallback guarantees ``no_sections_extracted`` will not fire on it either.

State it plainly: **the text-level invariant currently holds for PDF and not for HTML.**
The exemption below is keyed on *content type* while the real coverage depends on
*provider class*, so the drift test cannot see this widen — which is why it is written
down here instead. Closing it means either wiring ``content_gate`` into the remaining
providers (platform-control) or dropping the HTML exemption here, and the second is a
deliberate, measurable coverage drop that ADR-0047 says must be communicated before it is
measured, not slipped in.

Two structural checks — ``no_text_layer`` and ``no_sections_extracted`` — run on **every**
modality, because nothing upstream performs them at all.
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

# **Not** `content_gate`'s 3, and the divergence is measured rather than chosen.
#
# The upstream gate judges a whole *HTML portal page*, where the failure mode is a
# script-heavy navigation shell and marker density is high. This floor judges the extracted
# text of a *single PDF manifestation*, and the shortest real law in this repo is a
# municipal dog-tax decision of ~700 characters. Measured on the BS LexFind acceptance
# evidence (`tests/fixtures/bs_municipal_hundesteuer.json`, both in force):
#
#   Bettingen, Festsetzung der Hundesteuer     960 chars   3 markers   (2 without furniture)
#   Riehen, Festsetzung der Hundesteuer       1001 chars   3 markers   (2 without furniture)
#   Regierungsratsbeschluss, gefährliche Hunde 871 chars   5 markers   (4 without furniture)
#
# A floor of 3 puts the first two *exactly on* it — zero headroom — and their third marker
# is the word `Artikel` inside LexFind's own change-table boilerplate ("Änderungstabelle -
# Nach Artikel"), which is furniture, not legal structure. Strip the change table (a
# first-enactment record without one, another canton's template, a marginalia filter that
# drops it) and both fall to **2** and are withheld. That is the municipal rung of
# ADR-0033's own dog question being silently deleted from the corpus by its guard.
#
# So the honest question this floor answers is "does this text carry *any* legal structure
# at all", and the populations separate cleanly there: real law measures 2 at its worst,
# while a cover page, an error page and a consent interstitial all measure 0. One gives the
# shortest real law 2x headroom and still refuses every zero-marker interstitial.
#
# The relation to `content_gate` that matters is therefore **not stricter than upstream**,
# not equal to it — a DI floor above acquisition's would withhold a document acquisition
# already accepted as law. `tests/test_quarantine.py` pins that direction.
DEFAULT_MIN_LEGAL_MARKERS = 1

# Measured, not guessed, and calibrated on the *shortest* real law rather than the
# cantonal act: the smallest genuine document above is 871 characters, so a floor of 200
# leaves roughly 4x headroom. (The ZH Hundeverordnung, `tests/fixtures/zh_as_554_510.pdf`,
# normalises to 3 080 characters — but calibrating on it would have been calibrating on the
# comfortable case.) Low enough that a one-article communal ordinance is never refused,
# high enough that an image-only PDF (0 characters) and a cover sheet cannot pass.
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

        A *malformed* override must not silently lower a floor, so anything that does not
        parse as a non-negative integer leaves the configured default in place. A
        well-formed ``0`` is a different thing and is honoured: it turns that floor off for
        the source. That is a supported escape hatch — ADR-0047 is explicit that
        over-quarantine stalls ingestion — but it is a real off switch, so read a `0` here
        as "this source's floor is disabled", not as "no override was given".
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
