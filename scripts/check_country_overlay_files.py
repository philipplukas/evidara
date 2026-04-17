#!/usr/bin/env python3
"""Validate a country's overlay YAML files against schema + shared vocabularies.

Generalized from scripts/check_country_overlay_at.py. Given a country
ISO 3166-1 alpha-2 code, this script:

1. Verifies all four overlay files exist with matching `country_code`.
2. Structurally validates `jurisdiction_overlay` shape and
   `hierarchy_paths` regex.
3. Cross-checks `language_defaults.supported` against
   contracts/vocabularies/language.json.
4. Cross-checks `court_level_overlay.expected_levels` against the
   per-country entries in contracts/vocabularies/court-level.json.
5. Cross-checks `source_family_overlay.canonical` against the canonical
   set in contracts/vocabularies/source-family.json.
6. Verifies the jurisdiction vocab includes the country and that
   platform-control seeds include a `jur_<iso-lowercased>` entry.
7. If a per-country `required_authorities` profile is defined, verifies
   seeds include those authority IDs.
8. Optionally, if the `jsonschema` package is available, validates each
   overlay file against contracts/schemas/country-overlay.schema.json.

Companion to (and deliberately disjoint from) scripts/check_country_overlay.py,
which validates `source_blueprints.yaml` provider templates — different
concern, different set of files.

Usage:
    python3 scripts/check_country_overlay_files.py --country AT
    python3 scripts/check_country_overlay_files.py --country CH --root /path/to/repo
"""

from __future__ import annotations

import argparse
import json
import re
import sys
from pathlib import Path
from typing import Any

import yaml


OVERLAY_FILES = ("overlay.yaml", "reference-data.yaml", "user-content.yaml", "operator-content.yaml")

# Per-country minimum authority IDs that MUST appear in
# platform-control/seeds/reference/authorities.yaml for the overlay to be
# considered consistent. Additive — extend as overlays mature.
REQUIRED_AUTHORITIES: dict[str, set[str]] = {
    "AT": {"auth_at_ris", "auth_at_ogh", "auth_at_vfgh", "auth_at_vwgh"},
    "CH": {"auth_ch_fedlex", "auth_ch_bundesgericht"},
    "DE": {"auth_de_bundesrecht", "auth_de_bverfg", "auth_de_bgh"},
    "FR": {"auth_fr_legifrance", "auth_fr_ccass", "auth_fr_ce"},
    "IT": {"auth_it_gazzetta", "auth_it_normattiva", "auth_it_cassazione", "auth_it_cost"},
    "EU": {"auth_eu_eurlex", "auth_eu_cjeu"},
}

_HIERARCHY_PATH_RE = re.compile(r"^[a-z]{2}(/[a-z-]+(/[a-z0-9-]+)?)?$")


def _load_yaml(path: Path) -> dict[str, Any]:
    payload = yaml.safe_load(path.read_text(encoding="utf-8"))
    if not isinstance(payload, dict):
        raise ValueError(f"Expected YAML mapping in {path}")
    return payload


def _load_json(path: Path) -> dict[str, Any]:
    return json.loads(path.read_text(encoding="utf-8"))


def evaluate(country: str, root: Path) -> tuple[int, list[str]]:
    errors: list[str] = []
    country = country.upper()
    iso_lower = country.lower()

    overlay_root = root / "country-overlays" / iso_lower
    vocab_dir = root / "contracts" / "vocabularies"
    schema_file = root / "contracts" / "schemas" / "country-overlay.schema.json"
    seeds_dir = root / "platform-control" / "seeds" / "reference"

    required = {name: overlay_root / name for name in OVERLAY_FILES}
    required.update(
        {
            "jurisdiction.json": vocab_dir / "jurisdiction.json",
            "subdivisions.json": vocab_dir / "subdivisions.json",
            "source-family.json": vocab_dir / "source-family.json",
            "court-level.json": vocab_dir / "court-level.json",
            "language.json": vocab_dir / "language.json",
            "country-overlay.schema.json": schema_file,
            "jurisdictions.yaml": seeds_dir / "jurisdictions.yaml",
            "authorities.yaml": seeds_dir / "authorities.yaml",
        }
    )
    for label, path in required.items():
        if not path.exists():
            errors.append(f"Missing required file: {path} ({label})")
    if errors:
        return 1, errors

    overlay = _load_yaml(overlay_root / "overlay.yaml")
    reference_data = _load_yaml(overlay_root / "reference-data.yaml")
    user_content = _load_yaml(overlay_root / "user-content.yaml")
    operator_content = _load_yaml(overlay_root / "operator-content.yaml")

    for name, payload in [
        ("overlay.yaml", overlay),
        ("reference-data.yaml", reference_data),
        ("user-content.yaml", user_content),
        ("operator-content.yaml", operator_content),
    ]:
        if payload.get("country_code") != country:
            errors.append(f"{name} must declare country_code: {country}")

    jurisdiction_overlay = overlay.get("jurisdiction_overlay")
    if not isinstance(jurisdiction_overlay, dict):
        errors.append("overlay.yaml must define jurisdiction_overlay mapping")
        jurisdiction_overlay = {}

    canonical_codes = jurisdiction_overlay.get("canonical_codes") or []
    if country not in canonical_codes:
        errors.append(
            f"overlay.yaml jurisdiction_overlay.canonical_codes must include {country}"
        )

    hierarchy_paths = jurisdiction_overlay.get("hierarchy_paths") or []
    if not hierarchy_paths:
        errors.append("overlay.yaml jurisdiction_overlay.hierarchy_paths must be non-empty")
    else:
        for path_str in hierarchy_paths:
            if not isinstance(path_str, str) or not _HIERARCHY_PATH_RE.match(path_str):
                errors.append(
                    f"overlay.yaml invalid hierarchy_path {path_str!r}: must match "
                    f"<iso2>(/<tier>(/<subdivision>)?)?"
                )

    # ─── Vocab cross-references ──────────────────────────────
    jurisdiction_vocab = _load_json(vocab_dir / "jurisdiction.json")
    country_vocab = (
        jurisdiction_vocab.get("properties", {}).get("values", {}).get("properties", {})
    )
    if country not in country_vocab:
        errors.append(
            f"contracts/vocabularies/jurisdiction.json must include {country}"
        )

    language_vocab = _load_json(vocab_dir / "language.json")
    supported_languages = set(language_vocab.get("values", {}).keys())
    overlay_supported = []
    language_defaults = overlay.get("language_defaults")
    if isinstance(language_defaults, dict):
        overlay_supported = language_defaults.get("supported") or []
    for lang in overlay_supported:
        if lang not in supported_languages:
            errors.append(
                f"overlay.yaml language_defaults.supported references unknown language {lang!r}; "
                f"known: {sorted(supported_languages)}"
            )

    source_family_vocab = _load_json(vocab_dir / "source-family.json")
    known_source_families = set(source_family_vocab.get("values", {}).keys())
    source_family_overlay = overlay.get("source_family_overlay")
    overlay_canonical_sf = []
    if isinstance(source_family_overlay, dict):
        overlay_canonical_sf = source_family_overlay.get("canonical") or []
    for family in overlay_canonical_sf:
        if family not in known_source_families:
            errors.append(
                f"overlay.yaml source_family_overlay.canonical references unknown family "
                f"{family!r}; known: {sorted(known_source_families)}"
            )

    court_level_vocab = _load_json(vocab_dir / "court-level.json")
    country_levels = court_level_vocab.get("values", {}).get(country, {})
    known_levels = set(country_levels.keys())
    court_level_overlay = overlay.get("court_level_overlay")
    overlay_levels = []
    if isinstance(court_level_overlay, dict):
        overlay_levels = court_level_overlay.get("expected_levels") or []
    for level in overlay_levels:
        if level not in known_levels:
            errors.append(
                f"overlay.yaml court_level_overlay.expected_levels references unknown "
                f"level {level!r} for {country}; known: {sorted(known_levels)}"
            )

    # ─── Seeds cross-references ──────────────────────────────
    seed_jurisdictions = _load_yaml(seeds_dir / "jurisdictions.yaml").get("items") or []
    jur_id = f"jur_{iso_lower}"
    if not any(
        isinstance(item, dict) and item.get("jurisdiction_id") == jur_id
        for item in seed_jurisdictions
    ):
        errors.append(f"platform-control jurisdiction seeds must include {jur_id}")

    seed_authorities = _load_yaml(seeds_dir / "authorities.yaml").get("items") or []
    seed_authority_index = {
        item.get("authority_id"): item.get("jurisdiction_id")
        for item in seed_authorities
        if isinstance(item, dict)
    }
    existing_authority_ids = {
        aid for aid, jid in seed_authority_index.items() if jid == jur_id
    }

    required_auth = REQUIRED_AUTHORITIES.get(country, set())
    missing_in_seeds = sorted(required_auth - existing_authority_ids)
    if missing_in_seeds:
        errors.append(
            f"platform-control authority seeds missing {country} IDs: "
            f"{', '.join(missing_in_seeds)}"
        )

    # ─── reference-data.yaml must reference canonical seed IDs ───
    overlay_jurisdiction_id = reference_data.get("jurisdiction_id")
    if overlay_jurisdiction_id != jur_id:
        errors.append(
            f"reference-data.yaml jurisdiction_id must be {jur_id!r}, got "
            f"{overlay_jurisdiction_id!r}"
        )

    overlay_authority_ids = reference_data.get("authority_ids") or []
    if not overlay_authority_ids:
        errors.append("reference-data.yaml authority_ids must be a non-empty list")
    for aid in overlay_authority_ids:
        if aid not in seed_authority_index:
            errors.append(
                f"reference-data.yaml references unknown authority_id {aid!r}; "
                f"not present in platform-control/seeds/reference/authorities.yaml"
            )
        elif seed_authority_index[aid] != jur_id:
            errors.append(
                f"reference-data.yaml references authority_id {aid!r} whose "
                f"jurisdiction_id in seeds is {seed_authority_index[aid]!r}, "
                f"expected {jur_id!r}"
            )

    missing_in_overlay = sorted(required_auth - set(overlay_authority_ids))
    if missing_in_overlay:
        errors.append(
            f"reference-data.yaml must cite at minimum: {', '.join(missing_in_overlay)}"
        )

    # ─── Optional JSON-Schema layer ──────────────────────────
    try:
        import jsonschema  # type: ignore[import-untyped]
    except ImportError:
        jsonschema = None  # type: ignore[assignment]
    if jsonschema is not None:
        schema = _load_json(schema_file)
        file_payloads = {
            "overlay.yaml": overlay,
            "reference-data.yaml": reference_data,
            "user-content.yaml": user_content,
            "operator-content.yaml": operator_content,
        }
        for name, payload in file_payloads.items():
            try:
                jsonschema.validate(instance=payload, schema=schema)
            except jsonschema.ValidationError as exc:
                errors.append(
                    f"{name} schema validation failed: {exc.message} at {list(exc.path)}"
                )

    return (0, []) if not errors else (1, errors)


def main() -> int:
    parser = argparse.ArgumentParser(description="Validate a country overlay's YAML files.")
    parser.add_argument(
        "--country",
        required=True,
        help="ISO 3166-1 alpha-2 (e.g. CH, AT, DE, FR, IT, EU)",
    )
    parser.add_argument(
        "--root",
        default=".",
        help="Repo root (default: current working directory)",
    )
    args = parser.parse_args()
    exit_code, errors = evaluate(country=args.country, root=Path(args.root).resolve())
    if exit_code != 0:
        print(f"{args.country.upper()} overlay consistency check failed.", file=sys.stderr)
        for error in errors:
            print(f"- {error}", file=sys.stderr)
        return exit_code
    print(f"{args.country.upper()} overlay consistency check passed.")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
