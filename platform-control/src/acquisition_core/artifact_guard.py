"""Refuse captured bytes that are not the document they claim to be.

Every provider that fetches a manifestation faces the same failure: the transport
succeeds and the payload is not law. It has bitten twice, in ways that need
*different* checks — which is why there are two gates here, not one.

- **#631** — a ZH-Lex SPA served `200 text/html` for a statute URL, carrying the
  application shell rather than the statute. **This module cannot detect that**, and
  is not trying to: a navigation shell is well-formed HTML with real visible text, so
  it passes every byte-level check there is. It is caught by
  :func:`acquisition_core.content_gate.assess_legal_text_density`, added by #635,
  which counts legal-text markers and is inherited by every portal HTTP provider via
  ``portal_http_provider_base.py``.
- **#716** — `OpenAttachment?…` returned `200` with a **142-byte JavaScript redirect
  stub** where a PDF was expected. `content_gate` cannot detect *this*: its
  ``_ASSESSABLE_CONTENT_TYPES`` is HTML/XML only, so it abstains on binary bodies
  rather than guessing. That abstention is correct, and it is the gap this module
  fills.

**Use both.** They answer different questions — "are these the bytes I asked for?"
here, "does this text look like law?" there — and a provider fetching binary
manifestations needs the first before the second is even meaningful. Neither
subsumes the other, and this module must not grow a marker check of its own: the
vocabulary and threshold live in `content_gate`, and two opinions about what law
looks like is how they drift apart.

#731 calls the guard non-negotiable: *"A provider that cannot tell a stub from a
statute is worse than none."* Worse, because a silent stub capture reports coverage
the corpus does not have — the confident fabrication ADR-0033 exists to prevent.

**Scope, stated honestly.** This guard works on the *bytes as received*: declared
content type, format magic number, and a size floor. It defeats #716 and nothing
more, by design.

The gap the two gates together still leave: a **structurally valid PDF whose text is
not law** — a cover sheet, an error page, a consent interstitial. `content_gate`
abstains on `application/pdf`, and judging it needs extraction, which lives in
document-intelligence (ADR-0041's layout-aware normaliser). platform-control carries
no PDF stack, and adding one here would duplicate a capability one hop downstream —
the parallel-copy pattern that produced #675 and #713. That case therefore belongs to
DI's gate; see #731's acceptance criteria and ADR-0047.
"""

from __future__ import annotations

from dataclasses import dataclass

# Format signatures. A stub or an error page has none of these, whatever the
# server declared.
_MAGIC_BY_FORMAT: dict[str, tuple[bytes, ...]] = {
    "application/pdf": (b"%PDF-",),
    "application/zip": (b"PK\x03\x04", b"PK\x05\x06"),
}

# Markers of an HTML document. The #716 stub was HTML served as a PDF download, so
# an HTML opening in a binary manifestation is positive evidence of the failure,
# not merely absence of evidence.
_HTML_MARKERS: tuple[bytes, ...] = (
    b"<!doctype html",
    b"<html",
    b"<script",
    b"<meta http-equiv",
)

# How far in to look for a signature. Some servers emit a UTF-8 BOM or stray
# whitespace before the payload; a magic number further in than this is not a
# leading signature and should not be treated as one.
_SNIFF_WINDOW = 1024


@dataclass(frozen=True, slots=True)
class GuardResult:
    """Outcome of a capture check.

    ``reason`` is a stable, machine-readable slug rather than prose, because it is
    recorded on the skipped-resource record and read by operators deciding whether
    a source is broken or merely empty.
    """

    ok: bool
    reason: str | None = None
    detail: str | None = None

    def __bool__(self) -> bool:
        return self.ok


def looks_like_html(body: bytes) -> bool:
    """True when the payload opens as an HTML document."""
    head = body[:_SNIFF_WINDOW].lstrip().lower()
    return any(marker in head for marker in _HTML_MARKERS)


def has_format_magic(body: bytes, content_type: str) -> bool:
    """True when ``body`` opens with a signature for ``content_type``.

    Formats with no registered signature return ``True`` — this function answers
    "does the evidence contradict the claim", and for a text format there is no
    signature to contradict.
    """
    magics = _MAGIC_BY_FORMAT.get(content_type)
    if not magics:
        return True
    head = body[:_SNIFF_WINDOW].lstrip()
    return any(head.startswith(magic) for magic in magics)


def check_capture(
    *,
    body: bytes,
    expected_content_type: str,
    declared_content_type: str | None = None,
    min_bytes: int = 0,
) -> GuardResult:
    """Decide whether captured bytes may be carried into the artifact pipeline.

    Returns a falsy :class:`GuardResult` with a slug when the capture must be
    skipped. The caller records the reason rather than guessing — an unexplained
    skip and a successful capture are equally useless to an operator.

    Ordering is deliberate: the cheapest and most specific check runs first, so the
    recorded reason names the actual defect rather than a downstream symptom. A
    142-byte HTML stub declared as a PDF should report ``html_where_binary_expected``,
    not ``below_size_floor``.
    """
    if not body:
        return GuardResult(False, "empty_body", "zero bytes received")

    if (
        declared_content_type
        and expected_content_type
        and not declared_content_type.split(";")[0].strip().lower() == expected_content_type.lower()
    ):
        return GuardResult(
            False,
            "content_type_mismatch",
            f"declared {declared_content_type!r}, expected {expected_content_type!r}",
        )

    if expected_content_type in _MAGIC_BY_FORMAT:
        if looks_like_html(body):
            # #716 exactly: a redirect stub or login page dressed as a download.
            return GuardResult(
                False,
                "html_where_binary_expected",
                f"payload opens as HTML but {expected_content_type} was expected",
            )
        if not has_format_magic(body, expected_content_type):
            return GuardResult(
                False,
                "format_signature_missing",
                f"no {expected_content_type} signature in the first {_SNIFF_WINDOW} bytes",
            )

    if min_bytes and len(body) < min_bytes:
        # A real statute is not 142 bytes. The floor is per-source because the
        # honest minimum for a one-article communal ordinance is not the honest
        # minimum for a cantonal act.
        return GuardResult(
            False,
            "below_size_floor",
            f"{len(body)} bytes, floor is {min_bytes}",
        )

    return GuardResult(True)
