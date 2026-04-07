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
_SUPPORTED = {"AT", "DE", "FR", "IT", "CH"}
_TEMPLATE_ID_RE = re.compile(r"^[a-z0-9]+_[a-z0-9_]+$")


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


def _validate_template(
    overlay_id: str,
    template_id: str,
    payload: dict,
) -> list[str]:
    provider = payload.get("provider")
    if provider not in {"firecrawl", "deterministic_http", "ris_ogd"}:
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

    if provider == "deterministic_http":
        if not (
            _has_nonempty_str(payload.get("seed_url"))
            or _has_nonempty_str_list(payload.get("seed_urls"))
        ):
            return [
                f"Overlay '{overlay_id}' template '{template_id}' deterministic_http requires seed_url or seed_urls."
            ]
        return []

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
    parser.add_argument("--country", required=True, help="Country code (AT|DE|FR|IT|CH)")
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
