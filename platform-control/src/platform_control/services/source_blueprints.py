from __future__ import annotations

from functools import lru_cache
from pathlib import Path
from typing import Any

import yaml

from platform_control.errors import NotFoundError

_BLUEPRINTS_PATH = Path(__file__).resolve().parent.parent / "hierarchies" / "source_blueprints.yaml"


@lru_cache(maxsize=1)
def _load_blueprints() -> dict[str, Any]:
    with _BLUEPRINTS_PATH.open("r", encoding="utf-8") as handle:
        payload = yaml.safe_load(handle) or {}
    if not isinstance(payload, dict):
        raise ValueError("source_blueprints.yaml must contain a mapping at the root.")
    return payload


def resolve_source_blueprint(overlay_id: str, provider_template_id: str) -> dict[str, Any]:
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
    # Strip blueprint-level metadata before handing to AcquisitionSpec parsing.
    return {k: v for k, v in template_payload.items() if k != "enabled"}


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
