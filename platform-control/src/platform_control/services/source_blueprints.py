from __future__ import annotations

from functools import lru_cache
from pathlib import Path
from typing import Any
from urllib.parse import urlsplit

import yaml

from platform_control.errors import InvalidStateTransitionError, NotFoundError

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
# - `enabled`  -> is_source_blueprint_default_enabled
#                 (the *shipped default* of the config-owner key of the ADR-0030
#                 two-key lock; the operator-reachable override lives in the DB —
#                 see BlueprintEnablementService, #632)
# - `extractor_profile_id` -> resolve_blueprint_extractor_profile_id
#                 (source-version default applied by source_service)
_NON_SPEC_TEMPLATE_KEYS = frozenset({"enabled", "extractor_profile_id"})


# The only blueprint spec keys an operator may supply per source version — the
# "template plus my seeds" rung of the reuse ladder (#710, ADR-0046).
#
# Deliberately just the seeds. Every other key on a template is a claim the
# blueprint author made and that the ADR-0030 config key was turned *for*:
#   - `provider`                     -> which code key the run is judged against
#   - tenant_id / corpus_id / scope_type
#                                    -> where the documents land and who can see them
#   - trust_tier / source_origin_kind
#                                    -> the evidentiary claim attached to every artifact
#   - sparql_endpoint / base_url / canton_code / bfs_number / bundesland / regione
#                                    -> which portal is contacted at all
# Allowing any of those to be overridden would let an operator launder one
# template's earned enablement onto a different portal, a different tenant's
# corpus, or a stronger trust claim than the evidence supports.
_OVERRIDABLE_SPEC_KEYS = ("seed_url", "seed_urls")


def resolve_source_blueprint(overlay_id: str, provider_template_id: str) -> dict[str, Any]:
    """Return the template's acquisition-spec fields (non-spec keys removed)."""
    template_payload = _resolve_template(overlay_id, provider_template_id)
    return {k: v for k, v in template_payload.items() if k not in _NON_SPEC_TEMPLATE_KEYS}


def _origin(url: object) -> tuple[str, str] | None:
    """Return the ``(scheme, host)`` origin of a URL, lowercased."""
    if not isinstance(url, str) or not url.strip():
        return None
    parts = urlsplit(url)
    if not parts.scheme or not parts.netloc:
        return None
    return (parts.scheme.lower(), parts.netloc.lower())


def blueprint_seed_origins(blueprint: dict[str, Any]) -> set[tuple[str, str]]:
    """Return the ``(scheme, host)`` origins the template's own seeds point at.

    This set is the fence around an operator seed override: an override may pick
    different documents on a portal the blueprint already reaches, never a new
    portal. A template with no seeds of its own (``ris_ogd``, ``legifrance``)
    yields an empty set, which forbids overrides outright — those providers are
    not seed-driven and have no vetted origin to inherit.
    """
    origins: set[tuple[str, str]] = set()
    for key in _OVERRIDABLE_SPEC_KEYS:
        value = blueprint.get(key)
        candidates = value if isinstance(value, list) else [value]
        for candidate in candidates:
            origin = _origin(candidate)
            if origin is not None:
                origins.add(origin)
    return origins


def apply_blueprint_seed_override(
    blueprint: dict[str, Any],
    *,
    seed_url: str | None = None,
    seed_urls: list[str] | None = None,
) -> dict[str, Any]:
    """Merge operator-supplied seeds over a template's spec fields (#710).

    Only the seed keys the caller actually supplied are replaced; everything else
    — provider, tenant/corpus/scope, trust tier, portal config — is taken from
    the blueprint untouched, so the resulting spec is still the template's.

    Raises ``InvalidStateTransitionError`` if the template is not seed-driven or
    if any supplied seed leaves the template's own origins.
    """
    allowed = blueprint_seed_origins(blueprint)
    if not allowed:
        raise InvalidStateTransitionError(
            "This blueprint template declares no seed URLs, so it cannot take a seed "
            "override. Provide a full acquisition_spec instead."
        )

    supplied: list[str] = []
    if seed_url is not None:
        supplied.append(seed_url)
    if seed_urls is not None:
        supplied.extend(seed_urls)

    for candidate in supplied:
        origin = _origin(candidate)
        if origin is None or origin not in allowed:
            readable = ", ".join(sorted(f"{scheme}://{host}" for scheme, host in allowed))
            raise InvalidStateTransitionError(
                f"Seed override '{candidate}' is outside this blueprint template's own "
                f"origins ({readable}). A template's enablement is evidence about a "
                "specific portal, so an override may only choose different documents on "
                "that portal (ADR-0046)."
            )

    merged = dict(blueprint)
    if seed_url is not None:
        merged["seed_url"] = seed_url
    if seed_urls is not None:
        merged["seed_urls"] = list(seed_urls)
    return merged


def spec_is_blueprint_output(
    blueprint_spec: dict[str, Any],
    spec_payload: dict[str, Any],
) -> bool:
    """Is ``spec_payload`` still this blueprint's output, modulo operator seeds?

    Provenance on a source version means "this spec came from that template", and
    the run-launch path gates on it (ADR-0030). Since #710 a version may legally
    carry the template's spec with operator-chosen seeds, so an exact-equality
    test would drop provenance — and therefore drop the config-key gate — from
    exactly the versions this feature creates.

    The rule instead: every non-seed field must still match the template, and the
    seeds must still lie within the template's own origins.
    """
    if set(blueprint_spec) - set(_OVERRIDABLE_SPEC_KEYS) != set(spec_payload) - set(
        _OVERRIDABLE_SPEC_KEYS
    ):
        return False
    for key, expected in blueprint_spec.items():
        if key in _OVERRIDABLE_SPEC_KEYS:
            continue
        if spec_payload.get(key) != expected:
            return False

    allowed = blueprint_seed_origins(blueprint_spec)
    actual = blueprint_seed_origins(spec_payload)
    if actual == allowed:
        return True
    # Seeds differ from the template's: legal only if the template is seed-driven
    # and every seed still sits on an origin the template itself reaches.
    return bool(allowed) and bool(actual) and actual <= allowed


def is_source_blueprint_default_enabled(overlay_id: str, provider_template_id: str) -> bool:
    """Return the template's *shipped default* enablement (ADR-0030 config key).

    The flag defaults to the safe value: a template that omits `enabled`, or
    sets it to anything other than `true`, is NOT enabled by default.

    This is only the shipped default. The operator-reachable override — the key
    an operator actually flips after capturing acceptance-run evidence — lives in
    the database and is resolved by `BlueprintEnablementService` (#632), which
    consults this default only when no override row exists.
    """
    template_payload = _resolve_template(overlay_id, provider_template_id)
    return template_payload.get("enabled") is True


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
