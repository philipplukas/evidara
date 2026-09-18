"""Resolve a LexFind entity id from a jurisdiction id.

WHY THIS EXISTS. `coverage scaffold` refuses a `lexfind_api` template without
`--entity-id`, and nothing in the repo could supply one: `source_blueprints.yaml`
records three (ZH 26, BE 4, BS 6) and the help text repeated those three, so the
other 23 cantons were blocked on a number a person had to already know. LexFind
publishes the whole table unauthenticated, at the path platform-control's
provider already reads for reconciliation
(`services/lexfind_api_provider.py`, `_API_PREFIX` + `_ENTITIES_PATH`).

`tests/test_lexfind_entities.py` reads that provider and fails if the two paths
stop agreeing — this module is a second reader of one upstream contract, and the
copy is only safe while something checks it.

WHAT IT DOES NOT DO. It does not pick a canton. The caller supplies the
jurisdiction, and a code with no entity, or more than one, is refused rather than
resolved to a near match: scaffolding the wrong canton produces a template that
validates, runs, and silently captures another canton's law.
"""

from __future__ import annotations

from typing import Any

import httpx

from evidara_cli.client import HttpJsonError, request_json

#: Mirrors `_BASE_URL` + `_API_PREFIX` in platform-control's lexfind_api provider.
LEXFIND_BASE_URL = "https://www.lexfind.ch"
LEXFIND_API_PREFIX = "/api/frontend/v1"
#: Mirrors `_ENTITIES_PATH`. `extended` over plain `entities` for the per-entity
#: counts, which give the scaffolded template its denominator up front.
LEXFIND_ENTITIES_PATH = "entities/extended"

#: Jurisdictions whose canton code is not the tail of the id.
_SPECIAL_CODES = {"jur_ch_federal": "CH"}


class EntityResolutionError(RuntimeError):
    """The jurisdiction could not be resolved to exactly one LexFind entity.

    ``retriable`` separates "LexFind was unreachable" from "LexFind answered and
    has no such entity". The first is worth trying again; the second never is,
    and reporting both as one status would send an operator into a retry loop
    over a canton that does not exist.
    """

    def __init__(self, message: str, *, retriable: bool = False) -> None:
        super().__init__(message)
        self.retriable = retriable


def entities_url(language: str = "de") -> str:
    return f"{LEXFIND_BASE_URL}{LEXFIND_API_PREFIX}/{language}/{LEXFIND_ENTITIES_PATH}"


def entity_code_for(jurisdiction_id: str) -> str:
    """`jur_ch_ag` -> `AG`; `jur_ch_federal` -> `CH`.

    Refuses anything that is not a cantonal or federal Swiss jurisdiction. A
    municipal id (`jur_ch_gemeinde_261`) has no LexFind entity, and returning a
    plausible code for one would send the caller looking for a match that cannot
    exist.
    """
    if jurisdiction_id in _SPECIAL_CODES:
        return _SPECIAL_CODES[jurisdiction_id]
    if not jurisdiction_id.startswith("jur_ch_"):
        raise EntityResolutionError(
            f"{jurisdiction_id!r} is not a Swiss jurisdiction; LexFind covers CH only. "
            "Pass --entity-id explicitly if you know it."
        )
    tail = jurisdiction_id[len("jur_ch_") :]
    if len(tail) != 2 or not tail.isalpha():
        raise EntityResolutionError(
            f"{jurisdiction_id!r} is not a cantonal jurisdiction (expected jur_ch_<two-letter "
            "canton>). LexFind has entities for the 26 cantons and the Bund, not for communes."
        )
    return tail.upper()


def fetch_entities(
    *, language: str = "de", client: httpx.Client | None = None, timeout: float = 30.0
) -> list[dict[str, Any]]:
    """The published entity table. Read-only, unauthenticated, no side effect."""
    payload = request_json(
        "GET", entities_url(language), headers={}, client=client, timeout=timeout
    )
    if not isinstance(payload, list):
        raise EntityResolutionError(
            f"{entities_url(language)} did not return a list of entities; "
            f"got {type(payload).__name__}."
        )
    return [row for row in payload if isinstance(row, dict)]


def resolve_entity(
    jurisdiction_id: str, entities: list[dict[str, Any]]
) -> tuple[int, dict[str, Any]]:
    """Exactly one entity for the jurisdiction, or raise."""
    code = entity_code_for(jurisdiction_id)
    matches = [
        row
        for row in entities
        if str(row.get("abbreviation", "")).strip().upper() == code and row.get("id") is not None
    ]
    if not matches:
        published = ", ".join(sorted(str(r.get("abbreviation")) for r in entities)) or "(none)"
        raise EntityResolutionError(
            f"LexFind publishes no entity with abbreviation {code!r} "
            f"(for {jurisdiction_id}). Published: {published}."
        )
    if len(matches) > 1:
        ids = ", ".join(str(r.get("id")) for r in matches)
        raise EntityResolutionError(
            f"LexFind publishes {len(matches)} entities with abbreviation {code!r} (ids {ids}). "
            "Pass --entity-id to say which one."
        )
    row = matches[0]
    return int(row["id"]), row


def entity_denominator(row: dict[str, Any]) -> dict[str, Any]:
    """The per-entity counts, if the payload carried them.

    `entities/extended` nests them under `status` — the upstream's word, not a
    run status. Absent on the plain `entities` payload, so this reports what it
    found rather than defaulting to zero (ADR-0052).
    """
    counts = row.get("status")
    if not isinstance(counts, dict):
        return {"available": False}
    return {
        "available": True,
        "active_texts_of_law": counts.get("active_texts_of_law"),
        "total_texts_of_law": counts.get("total_texts_of_law"),
    }


def resolve_from_lexfind(
    jurisdiction_id: str,
    *,
    language: str = "de",
    client: httpx.Client | None = None,
) -> tuple[int, dict[str, Any]]:
    """Fetch and resolve in one step. Returns `(entity_id, provenance)`."""
    try:
        entities = fetch_entities(language=language, client=client)
    except HttpJsonError as exc:
        raise EntityResolutionError(
            f"Could not read {entities_url(language)} ({exc}). Pass --entity-id to scaffold "
            "without it.",
            retriable=True,
        ) from exc
    entity_id, row = resolve_entity(jurisdiction_id, entities)
    return entity_id, {
        "source": "lexfind_entities_extended",
        "url": entities_url(language),
        "abbreviation": row.get("abbreviation"),
        "entity_name": row.get("name"),
        "published_entities": len(entities),
        "denominator": entity_denominator(row),
    }
