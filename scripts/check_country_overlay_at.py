#!/usr/bin/env python3
"""Validate Austria country overlay consistency across contracts and seeds."""

from __future__ import annotations

from pathlib import Path
import sys
from typing import Any

import yaml


AT_OVERLAY_ROOT = Path("country-overlays/at")
OVERLAY_FILE = AT_OVERLAY_ROOT / "overlay.yaml"
USER_CONTENT_FILE = AT_OVERLAY_ROOT / "user-content.yaml"
OPERATOR_CONTENT_FILE = AT_OVERLAY_ROOT / "operator-content.yaml"
REFERENCE_DATA_FILE = AT_OVERLAY_ROOT / "reference-data.yaml"

JURISDICTION_VOCAB_FILE = Path("contracts/vocabularies/jurisdiction.json")
SEED_JURISDICTIONS_FILE = Path("platform-control/seeds/reference/jurisdictions.yaml")
SEED_AUTHORITIES_FILE = Path("platform-control/seeds/reference/authorities.yaml")


def load_yaml(path: Path) -> dict[str, Any]:
    payload = yaml.safe_load(path.read_text(encoding="utf-8"))
    if not isinstance(payload, dict):
        raise ValueError(f"Expected YAML mapping in {path}")
    return payload


def evaluate(
    overlay_file: Path = OVERLAY_FILE,
    user_content_file: Path = USER_CONTENT_FILE,
    operator_content_file: Path = OPERATOR_CONTENT_FILE,
    reference_data_file: Path = REFERENCE_DATA_FILE,
    jurisdiction_vocab_file: Path = JURISDICTION_VOCAB_FILE,
    seed_jurisdictions_file: Path = SEED_JURISDICTIONS_FILE,
    seed_authorities_file: Path = SEED_AUTHORITIES_FILE,
) -> tuple[int, list[str]]:
    errors: list[str] = []
    required_files = [
        overlay_file,
        user_content_file,
        operator_content_file,
        reference_data_file,
        jurisdiction_vocab_file,
        seed_jurisdictions_file,
        seed_authorities_file,
    ]
    for file_path in required_files:
        if not file_path.exists():
            errors.append(f"Missing required file: {file_path}")
    if errors:
        return 1, errors

    overlay = load_yaml(overlay_file)
    user_content = load_yaml(user_content_file)
    operator_content = load_yaml(operator_content_file)
    reference_data = load_yaml(reference_data_file)

    if overlay.get("country_code") != "AT":
        errors.append("overlay.yaml must declare country_code: AT")
    if user_content.get("country_code") != "AT":
        errors.append("user-content.yaml must declare country_code: AT")
    if operator_content.get("country_code") != "AT":
        errors.append("operator-content.yaml must declare country_code: AT")
    if reference_data.get("country_code") != "AT":
        errors.append("reference-data.yaml must declare country_code: AT")

    canonical_codes = (
        overlay.get("jurisdiction_overlay", {}).get("canonical_codes", [])
        if isinstance(overlay.get("jurisdiction_overlay"), dict)
        else []
    )
    if "AT" not in canonical_codes:
        errors.append("overlay.yaml jurisdiction_overlay.canonical_codes must include AT")

    vocab = jurisdiction_vocab_file.read_text(encoding="utf-8")
    if '"AT"' not in vocab:
        errors.append("contracts/vocabularies/jurisdiction.json must include AT")

    seed_jurisdictions = load_yaml(seed_jurisdictions_file).get("items", [])
    if not isinstance(seed_jurisdictions, list):
        errors.append("jurisdictions seed must contain list under items")
    else:
        has_jur_at = any(
            isinstance(item, dict)
            and item.get("jurisdiction_id") == "jur_at"
            and item.get("slug") == "at"
            for item in seed_jurisdictions
        )
        if not has_jur_at:
            errors.append("platform-control jurisdiction seeds must include jur_at/at")

    seed_authorities = load_yaml(seed_authorities_file).get("items", [])
    if not isinstance(seed_authorities, list):
        errors.append("authorities seed must contain list under items")
    else:
        required_authority_ids = {"auth_at_ris", "auth_at_ogh", "auth_at_vfgh", "auth_at_vwgh"}
        existing_authority_ids = {
            item.get("authority_id")
            for item in seed_authorities
            if isinstance(item, dict) and item.get("jurisdiction_id") == "jur_at"
        }
        missing_authorities = sorted(required_authority_ids - existing_authority_ids)
        if missing_authorities:
            errors.append(
                "platform-control authority seeds missing Austria IDs: "
                + ", ".join(missing_authorities)
            )

    return (0, []) if not errors else (1, errors)


def main() -> int:
    exit_code, errors = evaluate()
    if exit_code != 0:
        print("Austria overlay consistency check failed.", file=sys.stderr)
        for error in errors:
            print(f"- {error}", file=sys.stderr)
        return exit_code
    print("Austria overlay consistency check passed.")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
