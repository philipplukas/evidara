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
BLUEPRINTS = (
    REPO_ROOT
    / "platform-control"
    / "src"
    / "platform_control"
    / "hierarchies"
    / "source_blueprints.yaml"
)


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
        "source_blueprints.yaml no longer has templates for core live providers: "
        f"{sorted(missing)}."
    )


# Providers whose AcquisitionSpec union member is not landed yet, so their
# blueprint templates cannot be parsed by parse_acquisition_spec. These are
# pre-existing DE/IT subdivision scaffolds; adding their spec classes is
# tracked separately and out of scope for the CH work. Every other template
# MUST round-trip through parse_acquisition_spec (the source-creation path).
_SCAFFOLD_PROVIDERS_PENDING_SPEC = frozenset({"bundesland_http", "regione_http"})


def test_every_blueprint_template_parses_as_acquisition_spec() -> None:
    # Guards the source-creation path: `overlay_id + provider_template_id`
    # resolves a template that is fed to parse_acquisition_spec(). A template
    # carrying a field the provider's AcquisitionSpec forbids (extra="forbid")
    # or a provider with no union member fails here instead of at runtime when
    # an operator tries to create the source.
    from platform_control.schemas.source import parse_acquisition_spec
    from platform_control.services.source_blueprints import (
        list_source_blueprint_templates,
        resolve_source_blueprint,
    )

    failures: list[str] = []
    for row in list_source_blueprint_templates():
        if row["provider"] in _SCAFFOLD_PROVIDERS_PENDING_SPEC:
            continue
        template = resolve_source_blueprint(
            overlay_id=row["overlay_id"],
            provider_template_id=row["provider_template_id"],
        )
        try:
            parse_acquisition_spec(template)
        except Exception as exc:  # noqa: BLE001 - collect all failures for one assert
            failures.append(f"{row['overlay_id']}/{row['provider_template_id']}: {exc}")
    assert not failures, "blueprint templates that do not parse as AcquisitionSpec:\n" + "\n".join(
        failures
    )


def _seeded_extractor_profile_ids() -> set[str]:
    seed = (
        REPO_ROOT
        / "platform-control"
        / "src"
        / "platform_control"
        / "seeds"
        / "reference"
        / "extractor_profiles.yaml"
    )
    with seed.open("r", encoding="utf-8") as handle:
        payload = yaml.safe_load(handle) or {}
    return {item["extractor_profile_id"] for item in payload.get("items", [])}


def test_blueprint_extractor_profile_ids_exist_in_seed() -> None:
    # Any extractor_profile_id a template declares as a default must resolve to
    # a seeded profile, else source creation silently drops it (the default is
    # applied best-effort at runtime).
    with BLUEPRINTS.open("r", encoding="utf-8") as handle:
        payload = yaml.safe_load(handle) or {}
    seeded = _seeded_extractor_profile_ids()
    unknown: list[str] = []
    for overlay_id, overlay in (payload.get("overlays") or {}).items():
        for template_id, template in ((overlay or {}).get("provider_templates") or {}).items():
            if not isinstance(template, dict):
                continue
            profile_id = template.get("extractor_profile_id")
            if isinstance(profile_id, str) and profile_id not in seeded:
                unknown.append(f"{overlay_id}/{template_id} -> {profile_id}")
    assert not unknown, (
        "blueprint extractor_profile_id not in extractor_profiles.yaml:\n" + "\n".join(unknown)
    )
