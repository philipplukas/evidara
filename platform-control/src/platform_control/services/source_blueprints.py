from __future__ import annotations

from functools import lru_cache
from pathlib import Path
from typing import Any

import yaml

from platform_control.errors import BlueprintTemplateNotEnabledError, NotFoundError

_BLUEPRINTS_PATH = Path(__file__).resolve().parent.parent / "hierarchies" / "source_blueprints.yaml"


@lru_cache(maxsize=1)
def _load_blueprints() -> dict[str, Any]:
    with _BLUEPRINTS_PATH.open("r", encoding="utf-8") as handle:
        payload = yaml.safe_load(handle) or {}
    if not isinstance(payload, dict):
        raise ValueError("source_blueprints.yaml must contain a mapping at the root.")
    return payload


# Blueprint-level keys that are NOT provider config and therefore cannot be
# handed to AcquisitionSpec parsing (which forbids extra fields). They are not
# dropped — each has a dedicated accessor below that keeps the flag readable
# outside the spec:
# - `enabled`  -> is_source_blueprint_enabled / require_source_blueprint_enabled
#                 (config-owner key of the ADR-0030 two-key lock)
# - `extractor_profile_id` -> resolve_blueprint_extractor_profile_id
#                 (source-version default applied by source_service)
_NON_SPEC_TEMPLATE_KEYS = frozenset({"enabled", "extractor_profile_id"})


def resolve_source_blueprint(overlay_id: str, provider_template_id: str) -> dict[str, Any]:
    """Return the template's acquisition-spec fields (non-spec keys removed)."""
    template_payload = _resolve_template(overlay_id, provider_template_id)
    return {k: v for k, v in template_payload.items() if k not in _NON_SPEC_TEMPLATE_KEYS}


def is_source_blueprint_enabled(overlay_id: str, provider_template_id: str) -> bool:
    """Return whether the template is enabled for live acquisition (ADR-0030).

    The flag defaults to the safe value: a template that omits `enabled`, or
    sets it to anything other than `true`, is NOT enabled. An operator flips it
    to `true` only after capturing acceptance-run evidence for the template.
    """
    template_payload = _resolve_template(overlay_id, provider_template_id)
    return template_payload.get("enabled") is True


def require_source_blueprint_enabled(overlay_id: str, provider_template_id: str) -> None:
    """Raise BlueprintTemplateNotEnabledError unless the template is enabled.

    Config-owner key of the two-key lock. A template that has been removed from
    `source_blueprints.yaml` since a source version was created is treated as
    not enabled (fail closed) rather than as a 404.
    """
    try:
        enabled = is_source_blueprint_enabled(overlay_id, provider_template_id)
    except NotFoundError as exc:
        raise BlueprintTemplateNotEnabledError(
            f"Blueprint template '{overlay_id}/{provider_template_id}' no longer exists, "
            "so it cannot be launched for live acquisition."
        ) from exc
    if not enabled:
        raise BlueprintTemplateNotEnabledError(
            f"Blueprint template '{overlay_id}/{provider_template_id}' is not enabled for "
            "live acquisition (source_blueprints.yaml: enabled is not true). Capture "
            "acceptance-run evidence and flip `enabled: true` before launching runs "
            "(ADR-0030)."
        )


def resolve_blueprint_extractor_profile_id(
    overlay_id: str, provider_template_id: str
) -> str | None:
    """Return the template's default extractor_profile_id, if it declares one.

    Blueprint templates do not carry acquisition-spec fields for this; it is a
    source-version default that source_service applies when the create request
    does not specify an extractor_profile_id.
    """
    template_payload = _resolve_template(overlay_id, provider_template_id)
    value = template_payload.get("extractor_profile_id")
    return value if isinstance(value, str) and value.strip() else None


def _resolve_template(overlay_id: str, provider_template_id: str) -> dict[str, Any]:
    payload = _load_blueprints()
    overlays = payload.get("overlays")
    if not isinstance(overlays, dict):
        raise ValueError("source_blueprints.yaml missing overlays mapping.")

    overlay_payload = overlays.get(overlay_id)
    if not isinstance(overlay_payload, dict):
        raise NotFoundError(f"Unknown overlay_id '{overlay_id}'.")

    provider_templates = overlay_payload.get("provider_templates")
    if not isinstance(provider_templates, dict):
        raise ValueError(f"Overlay '{overlay_id}' is missing provider_templates mapping.")

    template_payload = provider_templates.get(provider_template_id)
    if not isinstance(template_payload, dict):
        raise NotFoundError(
            f"Unknown provider_template_id '{provider_template_id}' in overlay '{overlay_id}'."
        )
    return template_payload


def list_source_blueprint_templates() -> list[dict[str, str]]:
    payload = _load_blueprints()
    overlays = payload.get("overlays")
    if not isinstance(overlays, dict):
        raise ValueError("source_blueprints.yaml missing overlays mapping.")

    rows: list[dict[str, str]] = []
    for overlay_id, overlay_payload in sorted(overlays.items()):
        if not isinstance(overlay_payload, dict):
            continue
        provider_templates = overlay_payload.get("provider_templates")
        if not isinstance(provider_templates, dict):
            continue
        for provider_template_id, template_payload in sorted(provider_templates.items()):
            if not isinstance(template_payload, dict):
                continue
            provider = template_payload.get("provider")
            if not isinstance(provider, str):
                continue
            rows.append(
                {
                    "overlay_id": overlay_id,
                    "provider_template_id": provider_template_id,
                    "provider": provider,
                }
            )
    return rows
