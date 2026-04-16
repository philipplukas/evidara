"""Ensure source_blueprints.yaml templates reference known providers.

WHY THIS TEST EXISTS:
- `source_blueprints.yaml` addresses providers by string name.
- Providers are registered from `AcquisitionProvider` enum values.
- A typo or a renamed provider in the YAML produces a KeyError at
  run time, deep inside the acquisition path, where it's expensive to
  diagnose.
- This test catches the drift at build time.

WHAT WE DON'T TEST:
- Whether each template is logically configured (base_url correctness,
  language_codes validity, etc.) — that's owned by
  scripts/check_country_overlay.py which runs the per-provider
  structural checks.
"""

from __future__ import annotations

from pathlib import Path

import yaml

from platform_control.domain import AcquisitionProvider


REPO_ROOT = Path(__file__).resolve().parents[3]
BLUEPRINTS = REPO_ROOT / "platform-control" / "src" / "platform_control" / "hierarchies" / "source_blueprints.yaml"


def _referenced_provider_names() -> set[str]:
    with BLUEPRINTS.open("r", encoding="utf-8") as handle:
        payload = yaml.safe_load(handle) or {}
    overlays = payload.get("overlays") or {}
    referenced: set[str] = set()
    for overlay in overlays.values():
        templates = (overlay or {}).get("provider_templates") or {}
        for template in templates.values():
            if isinstance(template, dict) and isinstance(template.get("provider"), str):
                referenced.add(template["provider"])
    return referenced


def test_all_blueprint_providers_are_registered_enum_values() -> None:
    referenced = _referenced_provider_names()
    registered = {member.value for member in AcquisitionProvider}
    unknown = referenced - registered
    assert not unknown, (
        f"source_blueprints.yaml references unknown providers: {sorted(unknown)}. "
        f"Registered: {sorted(registered)}."
    )


def test_blueprint_references_at_least_the_core_providers() -> None:
    # Regression guard: if someone deletes a blueprint section we still
    # expect the four live-ready providers to have at least one template
    # so the CI surface covers the real acquisition path.
    referenced = _referenced_provider_names()
    core = {"firecrawl", "deterministic_http", "fedlex_sparql", "ris_ogd"}
    missing = core - referenced
    assert not missing, (
        f"source_blueprints.yaml no longer has templates for core live providers: {sorted(missing)}."
    )
