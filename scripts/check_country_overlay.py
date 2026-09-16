#!/usr/bin/env python3
from __future__ import annotations

import argparse
from pathlib import Path
import re

import yaml

ROOT = Path(__file__).resolve().parents[1]

_BLUEPRINTS_PATH = (
    ROOT / "platform-control" / "src" / "platform_control" / "hierarchies" / "source_blueprints.yaml"
)
_SUPPORTED = {"AT", "DE", "FR", "IT", "CH", "EU"}
_TEMPLATE_ID_RE = re.compile(r"^[a-z0-9]+_[a-z0-9_]+$")


_JURISDICTIONS_PATH = (
    ROOT / "platform-control" / "src" / "platform_control" / "seeds" / "reference" / "jurisdictions.yaml"
)


def _known_jurisdiction_ids() -> set[str]:
    """Every jurisdiction_id the canonical seed declares.

    Read from the seed rather than from a list here, so adding a canton in one
    place is enough. Cached on the function so a 2,169-entry file is parsed once
    per process rather than once per template.
    """
    cached = getattr(_known_jurisdiction_ids, "_cache", None)
    if cached is None:
        with _JURISDICTIONS_PATH.open("r", encoding="utf-8") as handle:
            payload = yaml.safe_load(handle) or {}
        cached = {
            str(item.get("jurisdiction_id"))
            for item in (payload.get("items") or [])
            if isinstance(item, dict) and item.get("jurisdiction_id")
        }
        _known_jurisdiction_ids._cache = cached  # type: ignore[attr-defined]
    return cached


def _load_blueprints() -> dict:
    with _BLUEPRINTS_PATH.open("r", encoding="utf-8") as handle:
        payload = yaml.safe_load(handle) or {}
    if not isinstance(payload, dict):
        raise ValueError("source_blueprints.yaml must be a mapping.")
    overlays = payload.get("overlays")
    if not isinstance(overlays, dict):
        raise ValueError("source_blueprints.yaml must contain overlays mapping.")
    return overlays


def evaluate(country: str) -> list[str]:
    normalized = country.strip().upper()
    if normalized not in _SUPPORTED:
        return [f"Unsupported country '{country}'. Supported: {', '.join(sorted(_SUPPORTED))}."]
    overlays = _load_blueprints()
    overlay_key = normalized.lower()
    overlay = overlays.get(overlay_key)
    if not isinstance(overlay, dict):
        return [f"Overlay '{overlay_key}' is missing in source_blueprints.yaml."]

    templates = overlay.get("provider_templates")
    if not isinstance(templates, dict):
        return [f"Overlay '{overlay_key}' is missing provider_templates mapping."]

    errors: list[str] = []
    for template_id, template_payload in sorted(templates.items()):
        if not isinstance(template_payload, dict):
            errors.append(
                f"Overlay '{overlay_key}' template '{template_id}' must be a mapping, got {type(template_payload).__name__}."
            )
            continue
        errors.extend(_validate_template(overlay_key, template_id, template_payload))
    return errors


# Providers whose templates are validated here. Keep in sync with
# `AcquisitionProvider` in platform-control/src/platform_control/domain.py;
# `test_blueprint_provider_parity.py` covers the enum-vs-blueprint side.
_SUPPORTED_PROVIDERS = {
    "firecrawl",
    "deterministic_http",
    "fedlex_sparql",
    "ris_ogd",
    "eur_lex_sparql",
    "bundesland_http",
    "regione_http",
    "canton_http",
    "lexfind_api",
    "gemeinde_http",
    "legifrance",
    "ch_court_decisions",
}


def _validate_template(
    overlay_id: str,
    template_id: str,
    payload: dict,
) -> list[str]:
    provider = payload.get("provider")
    if provider not in _SUPPORTED_PROVIDERS:
        return [
            f"Overlay '{overlay_id}' template '{template_id}' has unsupported provider '{provider}'."
        ]
    if not _TEMPLATE_ID_RE.match(template_id):
        return [
            f"Overlay '{overlay_id}' template '{template_id}' must match '<provider>_<domain>' naming."
        ]
    if not template_id.startswith(f"{provider}_"):
        return [
            f"Overlay '{overlay_id}' template '{template_id}' must start with '{provider}_'."
        ]

    # `jurisdiction_id` is OPTIONAL but, when declared, must name a jurisdiction the
    # seed actually has. A typo here is worse than an omission: an absent id reads as
    # "no template serves this jurisdiction" and fails closed, while a misspelt one
    # claims to serve a jurisdiction that does not exist and can never match anything.
    #
    # Three templates legitimately declare none — ris_ogd_lgbl_wien, ris_ogd_lgbl_noe
    # and regione_http_lombardia — because the seed carries sub-national entries for
    # CH and DE only. That is a gap in the seed, recorded rather than papered over
    # with the country-level id, which would claim Vienna's Landesrecht is federal
    # Austrian law.
    declared_jurisdiction = payload.get("jurisdiction_id")
    if declared_jurisdiction is not None:
        if not _has_nonempty_str(declared_jurisdiction):
            return [
                f"Overlay '{overlay_id}' template '{template_id}' jurisdiction_id must be "
                "a non-empty string when present (omit the key instead)."
            ]
        if declared_jurisdiction not in _known_jurisdiction_ids():
            return [
                f"Overlay '{overlay_id}' template '{template_id}' declares "
                f"jurisdiction_id '{declared_jurisdiction}', which is not in "
                "seeds/reference/jurisdictions.yaml."
            ]

    if provider == "firecrawl":
        mode = payload.get("mode", "crawl")
        if mode not in {"crawl", "batch_scrape"}:
            return [
                f"Overlay '{overlay_id}' template '{template_id}' has invalid firecrawl mode '{mode}'."
            ]
        if mode == "crawl" and not _has_nonempty_str(payload.get("seed_url")):
            return [
                f"Overlay '{overlay_id}' template '{template_id}' firecrawl crawl mode requires seed_url."
            ]
        if mode == "batch_scrape" and not _has_nonempty_str_list(payload.get("seed_urls")):
            return [
                f"Overlay '{overlay_id}' template '{template_id}' firecrawl batch_scrape mode requires seed_urls."
            ]
        return []

    if provider in {"deterministic_http", "fedlex_sparql", "eur_lex_sparql"}:
        if not (
            _has_nonempty_str(payload.get("seed_url"))
            or _has_nonempty_str_list(payload.get("seed_urls"))
        ):
            return [
                f"Overlay '{overlay_id}' template '{template_id}' {provider} requires seed_url or seed_urls."
            ]
        return []

    # LexFind (#731) is API-driven, so it has no seed URLs at all. A template
    # either SEARCHES a branch (non-empty `search_text` — the API rejects an empty
    # search with 400 and offers no list-everything call) or ENUMERATES a corpus
    # (`enumeration: systematic_digit_union`, #816), which does not search at all.
    # Neither means the template is inert.
    #
    # Mirrors `LexFindAcquisitionSpec._require_a_discovery_strategy`, restated here
    # because this gate runs against the YAML without importing platform-control.
    if provider == "lexfind_api":
        enumeration = payload.get("enumeration")
        if enumeration is not None:
            if enumeration != "systematic_digit_union":
                return [
                    f"Overlay '{overlay_id}' template '{template_id}' lexfind_api "
                    f"enumeration '{enumeration}' is not supported — the only "
                    "strategy is 'systematic_digit_union'."
                ]
            # An unscoped sweep would pull every entity LexFind carries.
            if not payload.get("entity_ids"):
                return [
                    f"Overlay '{overlay_id}' template '{template_id}' lexfind_api "
                    "enumeration requires entity_ids (ZH = 26); unscoped it would "
                    "sweep all 28 entities."
                ]
            return []
        if not _has_nonempty_str(payload.get("search_text")):
            return [
                f"Overlay '{overlay_id}' template '{template_id}' lexfind_api requires "
                "a non-empty search_text (the API has no list-everything call; use a "
                "systematic-number prefix such as '554') or "
                "enumeration: systematic_digit_union to hold the whole corpus."
            ]
        return []

    # Swiss federal court decisions (#530): seed URLs, discovery index URLs, or
    # a single seed URL are all valid targets.
    if provider == "ch_court_decisions":
        if not (
            _has_nonempty_str(payload.get("seed_url"))
            or _has_nonempty_str_list(payload.get("seed_urls"))
            or _has_nonempty_str_list(payload.get("index_urls"))
        ):
            return [
                f"Overlay '{overlay_id}' template '{template_id}' ch_court_decisions "
                "requires seed_url, seed_urls, or index_urls."
            ]
        return []

    if provider == "bundesland_http":
        errors: list[str] = []
        if not _has_nonempty_str(payload.get("bundesland")):
            errors.append(
                f"Overlay '{overlay_id}' template '{template_id}' bundesland_http requires bundesland (ISO 3166-2:DE)."
            )
        if not (
            _has_nonempty_str(payload.get("seed_url"))
            or _has_nonempty_str_list(payload.get("seed_urls"))
        ):
            errors.append(
                f"Overlay '{overlay_id}' template '{template_id}' bundesland_http requires seed_url or seed_urls."
            )
        return errors

    if provider == "regione_http":
        errors = []
        if not _has_nonempty_str(payload.get("regione")):
            errors.append(
                f"Overlay '{overlay_id}' template '{template_id}' regione_http requires regione (ISO 3166-2:IT)."
            )
        if not (
            _has_nonempty_str(payload.get("seed_url"))
            or _has_nonempty_str_list(payload.get("seed_urls"))
        ):
            errors.append(
                f"Overlay '{overlay_id}' template '{template_id}' regione_http requires seed_url or seed_urls."
            )
        return errors

    if provider == "canton_http":
        errors = []
        if not _has_nonempty_str(payload.get("canton_code")):
            errors.append(
                f"Overlay '{overlay_id}' template '{template_id}' canton_http requires canton_code (ISO 3166-2:CH)."
            )
        if not (
            _has_nonempty_str(payload.get("seed_url"))
            or _has_nonempty_str_list(payload.get("seed_urls"))
        ):
            errors.append(
                f"Overlay '{overlay_id}' template '{template_id}' canton_http requires seed_url or seed_urls."
            )
        return errors

    if provider == "gemeinde_http":
        errors = []
        # Swiss communes have no ISO 3166-2 code, so the portal allow-list is
        # keyed on the BFS/OFS Gemeindenummer — the same key the
        # `jur_ch_gemeinde_<bfs>` jurisdiction seeds are generated from.
        bfs_number = payload.get("bfs_number")
        if not isinstance(bfs_number, int) or isinstance(bfs_number, bool) or bfs_number < 1:
            errors.append(
                f"Overlay '{overlay_id}' template '{template_id}' gemeinde_http requires "
                "bfs_number (positive int, BFS/OFS Gemeindenummer)."
            )
        if not (
            _has_nonempty_str(payload.get("seed_url"))
            or _has_nonempty_str_list(payload.get("seed_urls"))
        ):
            errors.append(
                f"Overlay '{overlay_id}' template '{template_id}' gemeinde_http requires seed_url or seed_urls."
            )
        return errors

    if provider == "legifrance":
        if not _has_nonempty_str_list(payload.get("code_ids")):
            return [
                f"Overlay '{overlay_id}' template '{template_id}' legifrance requires code_ids."
            ]
        return []

    # ris_ogd
    if not _has_nonempty_str(payload.get("base_url")):
        return [
            f"Overlay '{overlay_id}' template '{template_id}' ris_ogd requires base_url."
        ]
    return []


def _has_nonempty_str(value: object) -> bool:
    return isinstance(value, str) and value.strip() != ""


def _has_nonempty_str_list(value: object) -> bool:
    return isinstance(value, list) and any(_has_nonempty_str(item) for item in value)


def parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(description="Validate country overlay provider templates.")
    parser.add_argument("--country", required=True, help="Country code (AT|DE|FR|IT|CH|EU)")
    return parser.parse_args()


def main() -> int:
    args = parse_args()
    errors = evaluate(args.country)
    if errors:
        for error in errors:
            print(f"ERROR: {error}")
        return 1
    print(f"Overlay '{args.country.upper()}' validation passed.")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
