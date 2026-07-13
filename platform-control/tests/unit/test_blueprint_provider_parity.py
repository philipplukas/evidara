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
# blueprint templates cannot be parsed by parse_acquisition_spec. Every
# template — including the DE/IT subdivision scaffolds, whose spec classes
# (BundeslandHttpAcquisitionSpec / RegioneHttpAcquisitionSpec) now exist —
# MUST round-trip through parse_acquisition_spec (the source-creation path).
_SCAFFOLD_PROVIDERS_PENDING_SPEC: frozenset[str] = frozenset()


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


def _templates() -> list[tuple[str, str, dict]]:
    with BLUEPRINTS.open("r", encoding="utf-8") as handle:
        payload = yaml.safe_load(handle) or {}
    rows: list[tuple[str, str, dict]] = []
    for overlay_id, overlay in (payload.get("overlays") or {}).items():
        for template_id, template in ((overlay or {}).get("provider_templates") or {}).items():
            if isinstance(template, dict):
                rows.append((overlay_id, template_id, template))
    return rows


def test_every_template_declares_enabled_explicitly() -> None:
    # `enabled` is the config-owner key of the ADR-0030 two-key lock and fails
    # closed: a template that omits it cannot launch runs. Requiring the value
    # to be stated keeps that a deliberate decision rather than an oversight —
    # a new template that silently never runs is as bad as one that runs when it
    # shouldn't.
    missing = [
        f"{overlay_id}/{template_id}"
        for overlay_id, template_id, template in _templates()
        if not isinstance(template.get("enabled"), bool)
    ]
    assert not missing, (
        "source_blueprints.yaml templates missing an explicit `enabled: true|false`:\n"
        + "\n".join(missing)
    )


def test_enabled_templates_only_reference_live_ready_providers() -> None:
    # Both keys of the lock must be consistent in the repo: enabling a template
    # whose provider is still a scaffold would land a config change that can only
    # ever produce ProviderNotLiveReadyError at dispatch. Catch it here instead.
    from platform_control.config import get_settings
    from platform_control.services.provider_registry_factory import build_provider_registry

    live_ready = build_provider_registry(get_settings()).live_ready_names()
    offenders = [
        f"{overlay_id}/{template_id} -> {template.get('provider')}"
        for overlay_id, template_id, template in _templates()
        if template.get("enabled") is True and template.get("provider") not in live_ready
    ]
    assert not offenders, (
        "source_blueprints.yaml enables templates whose provider is a scaffold "
        "(live_ready = False):\n" + "\n".join(offenders)
    )


def test_ch_fedlex_canary_template_stays_enabled() -> None:
    # scripts/ch-fedlex-fast-loop.sh launches a run from this template; the
    # two-key lock must not silently disable the canary (see AGENTS.md / #559).
    templates = {
        (overlay_id, template_id): template for overlay_id, template_id, template in _templates()
    }
    canary = templates[("ch", "fedlex_sparql_constitution_de")]
    assert canary["enabled"] is True
    assert canary["provider"] == "fedlex_sparql"


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
