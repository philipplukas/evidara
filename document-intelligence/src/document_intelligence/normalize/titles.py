"""Shared judgement about whether a candidate title is really a title.

Three copies of this predicate had drifted apart (`pipeline`, `ingest.docling_adapter`,
and platform-control's `events.artifact_bundle`), each with its own curated list of
strings to distrust. A curated list only catches placeholders someone has already
been bitten by, which is why `Fedlex` was caught and
`fedlex-data-admin-ch-eli-cc-2008-414-20230901-de-docx` was not (#771).

The filename rule below is the shape-based half: a portal that generates HTML from
an office document and leaves the source filename in `<title>` produces a string no
list can anticipate, but every instance looks the same.
"""

from __future__ import annotations

import re

# Curated placeholders — portal chrome that is present instead of a title.
_PLACEHOLDER_TITLES = frozenset(
    {
        "untitled document",
        "ris dokument",
        "fedlex",
        "input-de",
        "input-en",
        "input-fr",
        "input-it",
        "input-rm",
    }
)

# A filename that reached a title slot: no whitespace, separator-joined, ending in a
# document-format token. Anchored and format-terminated on purpose — `Tierschutzgesetz`
# is a legitimate single-word title and must not match, and neither must a hyphenated
# real title like `Verordnung-Nr-5`.
_FILENAME_TITLE_RE = re.compile(
    r"^[\w.]+(?:[-_.][\w.]+)*[-_.](?:docx?|pdf|html?|xhtml|xml|rtf|odt|odf|txt|md)$",
    re.IGNORECASE,
)


def looks_like_filename(title: str) -> bool:
    """True when the string is a filename rather than a title.

    Fedlex serves some consolidated acts as HTML generated from a .docx and leaves
    the source filename in `<title>`:

        fedlex-data-admin-ch-eli-cc-2008-414-20230901-de-docx

    Taken as a title it made the Tierschutzgesetz unfindable by its own name (#771).
    """
    candidate = title.strip()
    if not candidate or any(ch.isspace() for ch in candidate):
        return False
    # Two separators keeps the rule off short real titles that happen to end in a
    # format-like token; a leaked filename is always a multi-part path fragment.
    if sum(candidate.count(sep) for sep in "-_.") < 2:
        return False
    return bool(_FILENAME_TITLE_RE.match(candidate))


def is_placeholder_title(title: str | None) -> bool:
    """True when `title` must not be used as a document title.

    Callers fall back to their next-best source — an acquisition `title_hint`, the
    first body heading, or an explicit "Untitled document" — all of which are more
    honest than presenting portal chrome or a filename as the name of a law.
    """
    if title is None:
        return True
    candidate = title.strip()
    if not candidate:
        return True
    lowered = candidate.lower()
    if lowered in _PLACEHOLDER_TITLES:
        return True
    # RIS placeholder variants: "RIS — Dokument", "RIS – Dokument", "RIS - Dokument".
    collapsed = " ".join(lowered.split()).replace("—", "-").replace("–", "-")
    if collapsed.startswith("ris -") or collapsed.startswith("ris-"):
        return True
    return looks_like_filename(candidate)
