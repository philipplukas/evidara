"""Canonical jurisdiction ID resolver for document-intelligence.

Resolves source-level hints (ISO 3166-1 alpha-2 codes, slugs, common names,
and existing canonical IDs) to the canonical ``jur_*`` identifiers used in
published surfaces.

Reference data is embedded here rather than loaded from platform-control at
runtime to avoid a cross-component dependency in the processing path. The
mapping must be kept in sync with
``platform-control/seeds/reference/jurisdictions.yaml`` and
``contracts/vocabularies/jurisdiction.json``.
"""

from __future__ import annotations

from typing import Any

# Maps lowercase hint strings to canonical jurisdiction_id values.
# Covers:
#   - Already-canonical IDs (passthrough)
#   - ISO 3166-1 alpha-2 codes (upper and lower)
#   - Path slugs from the hierarchy (ch, at, ch-federal, at-federal)
#   - Common name aliases in DE, FR, IT, EN
_HINT_TO_CANONICAL: dict[str, str] = {
    # Passthrough: canonical IDs from platform-control/seeds/reference/jurisdictions.yaml
    "jur_ch": "jur_ch",
    "jur_ch_federal": "jur_ch_federal",
    "jur_at": "jur_at",
    "jur_at_federal": "jur_at_federal",
    # ISO 3166-1 alpha-2 codes → top-level jurisdiction
    "ch": "jur_ch",
    "at": "jur_at",
    "de": "jur_de",
    "li": "jur_li",
    # Hierarchy slugs
    "ch-federal": "jur_ch_federal",
    "at-federal": "jur_at_federal",
    # Common aliases — Switzerland
    "switzerland": "jur_ch",
    "schweiz": "jur_ch",
    "suisse": "jur_ch",
    "svizzera": "jur_ch",
    "svizra": "jur_ch",
    # Common aliases — Austria
    "austria": "jur_at",
    "österreich": "jur_at",
    "oesterreich": "jur_at",
    "autriche": "jur_at",
    "austria federal": "jur_at_federal",
    # Common aliases — Germany
    "germany": "jur_de",
    "deutschland": "jur_de",
    "allemagne": "jur_de",
    # Common aliases — Liechtenstein
    "liechtenstein": "jur_li",
}


def resolve_jurisdiction_id(hint: str | None) -> str | None:
    """Resolve a single jurisdiction hint to its canonical ID.

    Accepts canonical IDs (passthrough), ISO alpha-2 codes, hierarchy slugs,
    and common name aliases.  Returns *None* if the hint is empty or cannot
    be resolved.
    """
    if not hint:
        return None
    normalized = hint.strip().lower()
    if not normalized:
        return None
    # Fast path: already in the table
    if normalized in _HINT_TO_CANONICAL:
        return _HINT_TO_CANONICAL[normalized]
    # Forward-compatibility: unknown strings that already look like canonical IDs
    # (e.g. "jur_de" not yet in the table) are passed through as-is.
    if normalized.startswith("jur_"):
        return normalized
    return None


def resolve_jurisdiction_from_manifest(
    source_defaults: dict[str, Any],
    reference_context: dict[str, Any] | None = None,
) -> str | None:
    """Resolve the canonical jurisdiction ID from a bundle manifest.

    Resolution order:
    1. ``source_defaults["jurisdiction_id"]`` — may already be canonical or a hint.
    2. ``source_defaults["jurisdiction_hint"]`` — explicit hint field.
    3. ``reference_context["jurisdiction_hint"]`` — fallback from reference context.

    Returns *None* if no resolvable hint is found.
    """
    # Primary: jurisdiction_id field (canonical ID or raw hint)
    candidate = source_defaults.get("jurisdiction_id")
    if candidate:
        resolved = resolve_jurisdiction_id(str(candidate))
        if resolved is not None:
            return resolved

    # Secondary: explicit jurisdiction_hint in source_defaults
    hint = source_defaults.get("jurisdiction_hint")
    if hint:
        resolved = resolve_jurisdiction_id(str(hint))
        if resolved is not None:
            return resolved

    # Tertiary: hint in reference_context
    if reference_context:
        ctx_hint = reference_context.get("jurisdiction_hint") or reference_context.get("jurisdiction_id")
        if ctx_hint:
            resolved = resolve_jurisdiction_id(str(ctx_hint))
            if resolved is not None:
                return resolved

    return None
