"""Acquisition → DI hints: ``bundle_metadata.extraction_hints`` (v1).

Platform-Control (or other publishers) may attach structured crawl/extract
results here so DI can improve **recall** (fill title/type gaps) before
optional LLM calls — improving **precision** of LLM usage by shrinking the
gap set.

Schema v1 (object under ``bundle_metadata["extraction_hints"]``)
-----------------------------------------------------------------

All values are optional. Unknown keys are ignored (forward-compatible).

``title_hint`` (string)
    Preferred display title when the normalized primary title is missing or
    clearly generic (e.g. portal page titles).

``document_type_hint`` (string)
    Crawl-time type hint; same vocabulary as ``source_defaults.document_type_hint``
    where possible. Used only to satisfy the LLM skip gate when structured
    type is still missing.

``authority_display_hint`` (string)
    Human-readable authority line for UI or LLM context (not yet applied to
    canonical fields).

``effective_date_hint`` (string, ISO 8601 date recommended)
    Optional temporal anchor for downstream use.

``in_force_from_hint`` (string, ISO 8601 date)
    First day the norm is in force, as established at acquisition time (e.g.
    RIS ``Inkrafttretensdatum``, or the ``jolux:dateApplicability`` of the
    Fedlex consolidation actually selected). Applied to
    ``document.metadata["in_force_from"]``.

``in_force_until_hint`` (string, ISO 8601 date)
    Last day the norm is in force; absent while the norm is still in force
    (RIS omits ``Ausserkrafttretensdatum``; Fedlex leaves the current
    consolidation open-ended). Applied to
    ``document.metadata["in_force_until"]``.

    Both in-force hints are *omitted*, never defaulted, when acquisition could
    not establish the window — downstream in-force logic is four-valued and
    must be free to answer ``unknown`` rather than be handed a guess.

``docket_numbers`` (list of strings)
    Case numbers / Geschäftszahlen hints for LLM context or future IR.

``jurisdiction_hint`` (string)
    Optional ISO-like or internal jurisdiction slug when it differs from
    ``source_defaults.jurisdiction_id`` (diagnostics only in v1).

Versioning
----------

Consumers should treat missing ``extraction_hints`` as v0 (no hints).
A future ``extraction_hints_version`` key may appear; v1 is the implicit
default when the object is present.
"""

from __future__ import annotations

from typing import Any

_EXTRACTION_HINTS_V1_KEYS = frozenset(
    {
        "title_hint",
        "document_type_hint",
        "authority_display_hint",
        "effective_date_hint",
        "in_force_from_hint",
        "in_force_until_hint",
        "docket_numbers",
        "jurisdiction_hint",
    }
)


def coerce_extraction_hints(raw: Any) -> dict[str, Any]:
    """Return a sanitized ``extraction_hints`` dict for v1, or empty dict."""
    if not isinstance(raw, dict):
        return {}
    out: dict[str, Any] = {}
    for key in _EXTRACTION_HINTS_V1_KEYS:
        if key not in raw:
            continue
        val = raw[key]
        if val is None:
            continue
        if key == "docket_numbers":
            if isinstance(val, list):
                cleaned = [str(x).strip() for x in val if str(x).strip()]
                if cleaned:
                    out[key] = cleaned
            continue
        if isinstance(val, str) and val.strip():
            out[key] = val.strip()
    return out


def extraction_hints_from_bundle_metadata(bundle_metadata: dict[str, Any] | None) -> dict[str, Any]:
    """Parse ``extraction_hints`` from manifest ``bundle_metadata``."""
    if not bundle_metadata:
        return {}
    return coerce_extraction_hints(bundle_metadata.get("extraction_hints"))
