"""Draft a blueprint template for a jurisdiction that has none.

WHY THIS EXISTS. Adding the Nth canton is config, not code — `lexfind_api_zh_full`
differs from a Bern template only by `entity_ids: [4]` — but "config" meant hand-writing
YAML into `source_blueprints.yaml` from memory, 25 times, each edit a chance to typo a
jurisdiction id or omit the key that fails closed. The coverage queue can now say WHICH
jurisdiction needs a source (`register_source`, human-owned, because no template names
it); this turns that answer into the file that would fix it.

WHAT IT DELIBERATELY DOES NOT DO
--------------------------------
It does not write to `source_blueprints.yaml`, and it makes no API call. It prints YAML.
A template is a claim its author makes — which portal, which provider, which trust tier,
and eventually which `enabled: true` — and ADR-0030 puts that claim behind a human. So
this is `side_effect_level: none` and the operator commits the result, reviewing it as a
diff rather than as prose typed from memory.

`enabled: false` is not a parameter. The ADR-0030 config key fails closed and a template
is inert until an acceptance run earns it; a scaffold that could emit `true` would be a
way to skip that, in the one file where skipping it is invisible.

THE GUARANTEE THAT MATTERS
--------------------------
Whatever this emits must pass `scripts/check_country_overlay.py` — the same gate CI runs
over the committed file. A scaffold whose output the repo's own validator rejects is worse
than no scaffold: it produces confident, wrong YAML. `scripts/tests/test_template_scaffold.py`
asserts the round trip for every provider below, by scaffolding and then validating with
the real guard rather than a copy of its rules.
"""

from __future__ import annotations

from typing import Any

#: Providers this can draft, and what each needs beyond the common fields.
#:
#: Narrow on purpose. These are the three whose scope arguments are unambiguous and whose
#: rules `check_country_overlay` states explicitly. A provider absent here is REFUSED
#: rather than drafted from a guessed shape — emitting a plausible template for a provider
#: whose requirements nobody encoded is exactly the confident-and-wrong output this module
#: is supposed to prevent.
SUPPORTED_PROVIDERS = ("lexfind_api", "fedlex_sparql", "gemeinde_http")


class ScaffoldError(ValueError):
    """The request cannot produce a template that would validate."""


def _slugify(jurisdiction_id: str) -> str:
    """`jur_ch_be` -> `be`; `jur_ch_gemeinde_261` -> `gemeinde_261`."""
    for prefix in ("jur_ch_", "jur_de_", "jur_at_", "jur_it_", "jur_fr_", "jur_"):
        if jurisdiction_id.startswith(prefix):
            return jurisdiction_id[len(prefix) :]
    return jurisdiction_id


def default_template_id(provider: str, jurisdiction_id: str, suffix: str | None = None) -> str:
    """`<provider>_<jurisdiction>[_<suffix>]`.

    `check_country_overlay` requires a template id to start with `<provider>_` and to match
    `^[a-z0-9]+_[a-z0-9_]+$`, so the convention is a rule, not a preference.
    """
    parts = [provider, _slugify(jurisdiction_id)]
    if suffix:
        parts.append(suffix)
    return "_".join(p.strip("_") for p in parts if p)


def build_template(
    *,
    provider: str,
    jurisdiction_id: str,
    corpus_id: str,
    entity_ids: list[int] | None = None,
    seed_urls: list[str] | None = None,
    bfs_number: int | None = None,
    language: str = "de",
    document_type_hint: str = "legislation",
) -> dict[str, Any]:
    """The template body, as it should appear under `provider_templates`."""
    if provider not in SUPPORTED_PROVIDERS:
        raise ScaffoldError(
            f"cannot scaffold provider {provider!r}; supported: {', '.join(SUPPORTED_PROVIDERS)}. "
            "Add its rules here and to scripts/check_country_overlay.py together, or write the "
            "template by hand — a guessed shape is worse than none."
        )
    if not jurisdiction_id.startswith("jur_"):
        raise ScaffoldError(f"jurisdiction_id {jurisdiction_id!r} must start with 'jur_'")

    common: dict[str, Any] = {
        "provider": provider,
        "jurisdiction_id": jurisdiction_id,
        "tenant_id": "tenant_public",
        "corpus_id": corpus_id,
        "scope_type": "global_public",
        "source_origin_kind": "official_primary",
        "trust_tier": "authoritative",
        "language_codes": [language],
        "document_type_hint": document_type_hint,
    }

    if provider == "lexfind_api":
        if not entity_ids:
            raise ScaffoldError(
                "lexfind_api needs an entity id. Unscoped, enumeration would sweep all 28 "
                "entities. `coverage scaffold` resolves it from LexFind's published table "
                "for the jurisdiction; pass --entity-id to set it by hand."
            )
        common.update(
            {
                "enumeration": "systematic_digit_union",
                "entity_ids": list(entity_ids),
                "language": language,
                "results_per_page": 100,
                "max_pages": 40,
                "min_pdf_bytes": 2000,
                "extractor_profile_id": "exp_legislation_v1",
            }
        )
    elif provider == "fedlex_sparql":
        if not seed_urls:
            raise ScaffoldError("fedlex_sparql needs --seed-url, or use enumeration by hand")
        common.update(
            {
                "seed_urls": list(seed_urls),
                "sparql_endpoint": "https://fedlex.data.admin.ch/sparqlendpoint",
                "preferred_languages": [language],
                "query_mode": "work_to_expression",
                "max_expressions": 1,
            }
        )
    elif provider == "gemeinde_http":
        if bfs_number is None:
            raise ScaffoldError("gemeinde_http needs --bfs-number (Stadt Zürich = 261)")
        if not seed_urls:
            raise ScaffoldError("gemeinde_http needs --seed-url")
        common.update({"bfs_number": bfs_number, "seed_urls": list(seed_urls)})

    # Last, so it reads last in the emitted YAML — the key an operator must consciously
    # turn, after evidence, is the final line of what they are about to commit.
    common["enabled"] = False
    return common


def render_yaml(template_id: str, body: dict[str, Any], *, indent: int = 6) -> str:
    """Render as it would sit under `overlays.<country>.provider_templates`.

    Hand-rendered rather than `yaml.dump`, for two reasons: the indentation has to match
    the surrounding file so the output can be pasted without reflowing, and a dump would
    reorder or requote keys in ways that make the diff noisy for a reviewer.
    """
    pad = " " * indent
    inner = " " * (indent + 2)
    lines = [f"{pad}{template_id}:"]
    for key, value in body.items():
        if isinstance(value, bool):
            lines.append(f"{inner}{key}: {str(value).lower()}")
        elif isinstance(value, list):
            rendered = ", ".join(str(v) if not isinstance(v, str) else v for v in value)
            lines.append(f"{inner}{key}: [{rendered}]")
        else:
            lines.append(f"{inner}{key}: {value}")
    return "\n".join(lines) + "\n"
