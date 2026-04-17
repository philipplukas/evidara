"""Country-overlay loader with shared defaults + per-country override.

The country-overlays directory is the contract between humans (who
hand-edit YAML) and the rest of Evidara (which will eventually consume
the merged view). Without a loader, every consumer would re-implement
the merge logic and drift would compound.

Today no runtime service consumes country-overlay YAML — the files are
validated by `scripts/check_country_overlay_files.py`. This loader
exists so the first runtime consumer does not have to invent the merge
protocol, and so tests can assert merge behavior independently.

Merge rules (simple and documented):
1. Load `country-overlays/_shared/<file>` as the base layer (may be
   absent; treated as empty).
2. Load `country-overlays/<iso-lowercased>/<file>` as the override.
3. Deep-merge: dicts recurse, lists replace wholesale, scalars replace.
4. After merge, walk every string value and substitute the literal
   token `{country_code}` with the overlay's ISO 3166-1 alpha-2 code.

The `{country_code}` substitution is the ONLY templating this loader
supports. Any richer interpolation should live in the consumer, not in
the overlay files.
"""

from __future__ import annotations

from pathlib import Path
from typing import Any

import yaml


class OverlayLoadError(RuntimeError):
    """Raised when an overlay file is malformed or references a non-existent country."""


_OVERLAY_FILENAMES: dict[str, str] = {
    "overlay": "overlay.yaml",
    "reference_data": "reference-data.yaml",
    "user_content": "user-content.yaml",
    "operator_content": "operator-content.yaml",
}


def _load_yaml_if_exists(path: Path) -> dict[str, Any]:
    if not path.exists():
        return {}
    payload = yaml.safe_load(path.read_text(encoding="utf-8"))
    if payload is None:
        return {}
    if not isinstance(payload, dict):
        raise OverlayLoadError(f"Expected YAML mapping in {path}, got {type(payload).__name__}")
    return payload


def _deep_merge(base: dict[str, Any], override: dict[str, Any]) -> dict[str, Any]:
    """Return a new dict with `override` deep-merged on top of `base`.

    Dict values recurse; everything else replaces wholesale. Lists
    replace intentionally: per-country overlays declaring a list must
    specify the whole list, not a patch.
    """
    result: dict[str, Any] = dict(base)
    for key, override_value in override.items():
        base_value = result.get(key)
        if isinstance(base_value, dict) and isinstance(override_value, dict):
            result[key] = _deep_merge(base_value, override_value)
        else:
            result[key] = override_value
    return result


def _substitute_country_code(value: Any, country_code: str) -> Any:
    """Walk the structure replacing `{country_code}` in any string leaf."""
    if isinstance(value, str):
        return value.replace("{country_code}", country_code)
    if isinstance(value, dict):
        return {k: _substitute_country_code(v, country_code) for k, v in value.items()}
    if isinstance(value, list):
        return [_substitute_country_code(item, country_code) for item in value]
    return value


def _load_merged(
    *,
    kind: str,
    country_code: str,
    overlays_root: Path,
) -> dict[str, Any]:
    if kind not in _OVERLAY_FILENAMES:
        raise OverlayLoadError(f"Unknown overlay kind {kind!r}")
    filename = _OVERLAY_FILENAMES[kind]
    iso_lower = country_code.lower()

    country_dir = overlays_root / iso_lower
    if not country_dir.is_dir():
        raise OverlayLoadError(
            f"Country overlay directory missing: {country_dir} "
            f"(country_code={country_code!r})"
        )

    shared = _load_yaml_if_exists(overlays_root / "_shared" / filename)
    country = _load_yaml_if_exists(country_dir / filename)

    merged = _deep_merge(shared, country)
    return _substitute_country_code(merged, country_code.upper())


def load_user_content(country_code: str, overlays_root: Path) -> dict[str, Any]:
    """Return the merged user-facing content payload for a country."""
    return _load_merged(kind="user_content", country_code=country_code, overlays_root=overlays_root)


def load_operator_content(country_code: str, overlays_root: Path) -> dict[str, Any]:
    """Return the merged operator-facing content payload for a country."""
    return _load_merged(kind="operator_content", country_code=country_code, overlays_root=overlays_root)


def load_overlay(country_code: str, overlays_root: Path) -> dict[str, Any]:
    """Return the structural overlay payload for a country (no shared base today)."""
    return _load_merged(kind="overlay", country_code=country_code, overlays_root=overlays_root)


def load_reference_data(country_code: str, overlays_root: Path) -> dict[str, Any]:
    """Return the reference-data citation payload for a country (no shared base today)."""
    return _load_merged(kind="reference_data", country_code=country_code, overlays_root=overlays_root)
