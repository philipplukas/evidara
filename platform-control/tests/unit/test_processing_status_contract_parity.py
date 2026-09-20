"""`ProcessingStatus` and the event contract must declare the same statuses (#1045).

Two declarations of one set, in two languages, joined by nothing. The contract's enum
is what document-intelligence may put on the wire; `ProcessingStatus` is what this
service will accept and store. A member in one and not the other fails in exactly one
direction and never in tests:

* in the contract only — DI can emit it, the ingest endpoint rejects it as an invalid
  enum value, and the refusal is a 422 nobody is watching;
* in `ProcessingStatus` only — this service declares a status nothing may ever send,
  which is the #1045 defect itself: a counter, a read model and a reason rule built on
  a value with no producer.

`document-intelligence/tests/test_status_producers.py` holds the other half — that a
declared status has a *writer*. This holds that the two declarations agree on what is
declared at all.
"""

from __future__ import annotations

import json
from pathlib import Path
from typing import Any

from platform_control.domain import STATUSES_REQUIRING_A_REASON, ProcessingStatus

_SCHEMA = (
    Path(__file__).resolve().parents[3]
    / "contracts"
    / "events"
    / "document-processing-status-updated.schema.json"
)


def _payload_schema() -> dict[str, Any]:
    schema = json.loads(_SCHEMA.read_text(encoding="utf-8"))
    for branch in schema["allOf"]:
        payload = branch.get("properties", {}).get("payload")
        if payload:
            return payload
    raise AssertionError(f"{_SCHEMA.name} no longer declares a payload schema")


def test_contract_enum_matches_processing_status() -> None:
    """MUTATION: add a member to `ProcessingStatus` without touching the schema and
    this fails naming it, instead of shipping a status nothing can send."""
    contract_statuses = set(_payload_schema()["properties"]["status"]["enum"])
    assert contract_statuses, "the contract no longer enumerates statuses at all"

    assert contract_statuses == {member.value for member in ProcessingStatus}


def test_the_contract_requires_a_reason_for_exactly_the_statuses_we_do() -> None:
    """The reason rule is written twice — in JSON Schema and in Pydantic — and the two
    must bind the same statuses.

    They did not, for nine months. The enum carried `quarantined` from contract 0.22.0
    (#731) and `STATUSES_REQUIRING_A_REASON` carried it too, while the schema's `if`
    still said `status == "failed"` — so the one event ADR-0047 requires to carry a
    reason slug was the one shape the contract refused. Nothing noticed, because
    nothing emitted it (#1045).
    """
    conditions = _payload_schema()["allOf"]
    assert len(conditions) == 1, "the reason rule is expected to be the only conditional"

    condition = conditions[0]["if"]["properties"]["status"]
    # `const` is the pre-#1045 single-status form; it cannot express two.
    schema_statuses = set(condition.get("enum", [])) or {condition["const"]}

    assert schema_statuses == {member.value for member in STATUSES_REQUIRING_A_REASON}

    # And the rule still bites: required on one side, null on the other.
    assert set(conditions[0]["then"]["required"]) == {"error_code", "error_summary"}
    assert conditions[0]["else"]["properties"]["error_code"]["type"] == "null"
