from __future__ import annotations

import re
from pathlib import Path
from typing import Any
from unittest.mock import patch

import pytest

from evidara_cli.client import HttpJsonError
from evidara_cli.lexfind_entities import (
    LEXFIND_API_PREFIX,
    LEXFIND_BASE_URL,
    LEXFIND_ENTITIES_PATH,
    EntityResolutionError,
    entities_url,
    entity_code_for,
    entity_denominator,
    resolve_entity,
    resolve_from_lexfind,
)
from evidara_cli.repo_root import resolve_repo_root

_PROVIDER = "platform-control/src/platform_control/services/lexfind_api_provider.py"

#: Shaped like the live payload, including `status` holding counts rather than a status.
_ENTITIES: list[dict[str, Any]] = [
    {
        "id": 1,
        "abbreviation": "AG",
        "name": "Aargau",
        "status": {"total_texts_of_law": 983, "active_texts_of_law": 463},
    },
    {
        "id": 26,
        "abbreviation": "ZH",
        "name": "Zürich",
        "status": {"total_texts_of_law": 1378, "active_texts_of_law": 944},
    },
    {
        "id": 27,
        "abbreviation": "CH",
        "name": "Bund",
        "status": {"total_texts_of_law": 6764, "active_texts_of_law": 5333},
    },
]


def test_entity_code_derives_canton_from_jurisdiction() -> None:
    assert entity_code_for("jur_ch_ag") == "AG"
    assert entity_code_for("jur_ch_zh") == "ZH"
    assert entity_code_for("jur_ch_federal") == "CH"


@pytest.mark.parametrize(
    "jurisdiction_id",
    ["jur_ch_gemeinde_261", "jur_de_by", "jur_ch", "jur_ch_zurich"],
)
def test_entity_code_refuses_anything_that_is_not_a_canton(jurisdiction_id: str) -> None:
    """A commune has no LexFind entity. Returning a plausible code for one would
    send the caller hunting a match that cannot exist."""
    with pytest.raises(EntityResolutionError):
        entity_code_for(jurisdiction_id)


def test_resolve_entity_finds_the_canton() -> None:
    entity_id, row = resolve_entity("jur_ch_ag", _ENTITIES)
    assert entity_id == 1
    assert row["name"] == "Aargau"


def test_resolve_entity_refuses_an_unpublished_canton() -> None:
    with pytest.raises(EntityResolutionError) as exc:
        resolve_entity("jur_ch_vd", _ENTITIES)
    # The refusal names what IS published, so the operator can see the gap.
    assert "AG" in str(exc.value)


def test_resolve_entity_refuses_an_ambiguous_abbreviation() -> None:
    """Two entities sharing a code must not resolve to whichever sorts first —
    scaffolding the wrong canton yields a template that validates and captures
    another canton's law."""
    doubled = [*_ENTITIES, {"id": 99, "abbreviation": "AG", "name": "Aargau (alt)"}]
    with pytest.raises(EntityResolutionError) as exc:
        resolve_entity("jur_ch_ag", doubled)
    assert "99" in str(exc.value)


def test_denominator_reports_absence_rather_than_zero() -> None:
    """ADR-0052: a payload without counts is unknown, not empty."""
    assert entity_denominator({"id": 1})["available"] is False
    present = entity_denominator(_ENTITIES[0])
    assert present["available"] is True
    assert present["active_texts_of_law"] == 463


@patch("evidara_cli.lexfind_entities.request_json", return_value=_ENTITIES)
def test_resolve_from_lexfind_reports_its_provenance(req: Any) -> None:
    entity_id, provenance = resolve_from_lexfind("jur_ch_ag")
    assert entity_id == 1
    assert provenance["source"] == "lexfind_entities_extended"
    assert provenance["url"] == entities_url("de")
    assert provenance["denominator"]["active_texts_of_law"] == 463
    assert req.call_args.args[0] == "GET"


@patch("evidara_cli.lexfind_entities.request_json")
def test_unreachable_lexfind_is_retriable_not_terminal(req: Any) -> None:
    req.side_effect = HttpJsonError("boom", status_code=None, body="")
    with pytest.raises(EntityResolutionError) as exc:
        resolve_from_lexfind("jur_ch_ag")
    assert exc.value.retriable is True


@patch("evidara_cli.lexfind_entities.request_json", return_value={"not": "a list"})
def test_a_non_list_payload_is_refused(_req: Any) -> None:
    with pytest.raises(EntityResolutionError):
        resolve_from_lexfind("jur_ch_ag")


def test_entities_path_still_matches_the_provider() -> None:
    """This module is a SECOND reader of one upstream contract.

    platform-control's provider owns the same three constants. Nothing makes them
    move together, so if that file changes its path this test fails here rather
    than the CLI silently reading a 404 and reporting "LexFind unreachable".
    """
    source = (resolve_repo_root() / _PROVIDER).read_text(encoding="utf-8")

    def literal(name: str) -> str:
        match = re.search(rf'^{name} = "([^"]+)"', source, re.MULTILINE)
        assert match is not None, f"{name} is gone from {_PROVIDER}"
        return match.group(1)

    assert literal("_BASE_URL") == LEXFIND_BASE_URL
    assert literal("_API_PREFIX") == LEXFIND_API_PREFIX
    assert literal("_ENTITIES_PATH") == LEXFIND_ENTITIES_PATH


def test_the_drift_guard_reads_a_file_that_exists() -> None:
    """A guard that silently finds no file asserts nothing. This fails if the
    provider moves, rather than letting the test above pass over an empty read."""
    assert (resolve_repo_root() / Path(_PROVIDER)).is_file()
