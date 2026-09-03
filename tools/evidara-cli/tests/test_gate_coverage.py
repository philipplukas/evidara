"""The excluded / not-evaluated split, and the one rule that escalates it (#744).

`skipped_gates` collapsed two opposite claims into one list: a gate nobody asked for
(still evidence) and a gate that was asked for and could not run (a hole). These assert
the split, the escalation, and the conservative reading of the legacy shape.
"""

from __future__ import annotations

import json

import pytest

from evidara_cli.coverage import acceptance_evidence_verdict, flip_refusals
from evidara_cli.gate_coverage import (
    EVIDENCE_GATE_COVERAGE_UNKNOWN,
    EVIDENCE_GATE_NOT_EVALUATED,
    gate_coverage_verdict,
    load_evidence_bundle,
)

_GOOD_RUN = {
    "run_id": "run_1",
    "status": "completed",
    "mode": "acceptance",
    "refused": False,
    "captured_resources_count": 5,
}


def bundle(**checks: object) -> dict:
    return {"verdict": "pass", "checks": {"captured_count": 3, **checks}}


# --- the split ---------------------------------------------------------------------


def test_an_excluded_gate_is_still_acceptance_evidence() -> None:
    verdict = gate_coverage_verdict(
        bundle(
            gate_coverage=[
                {
                    "gate": "title_ok",
                    "outcome": "excluded",
                    "reason": "no_expected_title_declared",
                }
            ],
            skipped_gates=["title_ok"],
        )
    )

    assert verdict["is_acceptance_evidence"] is True
    assert verdict["refusals"] == []
    assert [e["gate"] for e in verdict["excluded"]] == ["title_ok"]
    assert verdict["not_evaluated"] == []


def test_a_not_evaluated_gate_refuses_and_names_itself() -> None:
    verdict = gate_coverage_verdict(
        bundle(
            gate_coverage=[
                {
                    "gate": "indexed_title_ok",
                    "outcome": "not_evaluated",
                    "reason": "no_legal_search_url",
                }
            ],
            skipped_gates=["indexed_title_ok"],
        )
    )

    assert verdict["is_acceptance_evidence"] is False
    assert [r["code"] for r in verdict["refusals"]] == [EVIDENCE_GATE_NOT_EVALUATED]
    # Naming which gate, and why, is the point: "some gate did not run" is not
    # actionable and reads as boilerplate.
    detail = verdict["refusals"][0]["detail"]
    assert "indexed_title_ok" in detail
    assert "no_legal_search_url" in detail


def test_one_not_evaluated_gate_disqualifies_a_bundle_full_of_excluded_ones() -> None:
    # The mixed case is the one a single list could never express.
    verdict = gate_coverage_verdict(
        bundle(
            gate_coverage=[
                {"gate": "title_ok", "outcome": "excluded", "reason": "x"},
                {"gate": "body_lang_hint_ok", "outcome": "excluded", "reason": "y"},
                {"gate": "indexed_title_ok", "outcome": "not_evaluated", "reason": "z"},
            ]
        )
    )

    assert verdict["is_acceptance_evidence"] is False
    assert len(verdict["excluded"]) == 2
    assert [e["gate"] for e in verdict["not_evaluated"]] == ["indexed_title_ok"]


def test_full_coverage_reports_no_refusal() -> None:
    verdict = gate_coverage_verdict(bundle(gate_coverage=[], skipped_gates=[]))

    assert verdict["is_acceptance_evidence"] is True
    assert verdict["reported"] is True
    assert verdict["source_shape"] == "gate_coverage"


def test_an_unrecognised_outcome_is_read_as_not_evaluated() -> None:
    # Fail-closed: a future or misspelled outcome must not be waved through as a pass.
    verdict = gate_coverage_verdict(
        bundle(gate_coverage=[{"gate": "title_ok", "outcome": "probably_fine"}])
    )

    assert verdict["is_acceptance_evidence"] is False
    assert verdict["not_evaluated"][0]["gate"] == "title_ok"


# --- the legacy shape ---------------------------------------------------------------


def test_a_legacy_bundle_is_read_as_not_evaluated_not_excluded() -> None:
    # Four of the five persisted bundles are the only acceptance evidence this project
    # has. A pre-split bundle cannot say WHY a gate is absent, so the unknown reason is
    # read the safe way: it may refuse evidence that was fine, never accept evidence
    # that is not.
    verdict = gate_coverage_verdict(bundle(skipped_gates=["title_ok"]))

    assert verdict["source_shape"] == "legacy_skipped_gates"
    assert verdict["is_acceptance_evidence"] is False
    assert verdict["excluded"] == []
    assert verdict["not_evaluated"][0]["reason"] == "reason_not_recorded"


def test_a_legacy_bundle_with_an_empty_list_still_passes() -> None:
    # This is why the conservative read costs nothing today: every persisted bundle
    # reports `skipped_gates: []`, which means the same thing under both readings.
    verdict = gate_coverage_verdict(bundle(skipped_gates=[]))

    assert verdict["source_shape"] == "legacy_skipped_gates"
    assert verdict["is_acceptance_evidence"] is True


def test_the_persisted_bundles_survive_the_change(tmp_path) -> None:
    from pathlib import Path

    repo_root = Path(__file__).resolve().parents[3]
    bundles = sorted((repo_root / "docs" / "runbooks" / "evidence").rglob("*.json"))
    assert bundles, "no evidence bundles found — this test would be vacuous"

    refused = []
    for path in bundles:
        parsed = load_evidence_bundle(path)
        verdict = gate_coverage_verdict(parsed)
        # A bundle that never reported gate coverage at all is legitimately unknown;
        # one that reported it must not become un-citable because of this change.
        if verdict["source_shape"] != "absent" and not verdict["is_acceptance_evidence"]:
            refused.append(path.name)
    assert refused == [], f"the split newly disqualified existing evidence: {refused}"


def test_a_bundle_that_reports_no_coverage_at_all_is_unknown_not_clean() -> None:
    verdict = gate_coverage_verdict({"verdict": "pass", "checks": {"captured_count": 3}})

    assert verdict["reported"] is False
    assert verdict["source_shape"] == "absent"
    assert [r["code"] for r in verdict["refusals"]] == [EVIDENCE_GATE_COVERAGE_UNKNOWN]


def test_no_bundle_at_all_refuses_nothing() -> None:
    # Citing no bundle is the caller's decision to make; the module does not invent a
    # refusal for a file that was never offered.
    verdict = gate_coverage_verdict(None)

    assert verdict["reported"] is False
    assert verdict["is_acceptance_evidence"] is True
    assert verdict["refusals"] == []


# --- loading -------------------------------------------------------------------------


def test_an_unreadable_bundle_raises_rather_than_reading_as_clean(tmp_path) -> None:
    path = tmp_path / "summary.json"
    path.write_text("{not json", encoding="utf-8")

    with pytest.raises(json.JSONDecodeError):
        load_evidence_bundle(path)

    with pytest.raises(OSError):
        load_evidence_bundle(tmp_path / "missing.json")


def test_a_non_object_bundle_is_rejected(tmp_path) -> None:
    path = tmp_path / "summary.json"
    path.write_text("[]", encoding="utf-8")

    with pytest.raises(ValueError):
        load_evidence_bundle(path)


# --- the escalation reaches the flip ------------------------------------------------


def test_the_acceptance_verdict_folds_the_gate_refusal_in() -> None:
    verdict = acceptance_evidence_verdict(
        run=_GOOD_RUN,
        execution_mode="live",
        evidence_bundle=bundle(
            gate_coverage=[{"gate": "indexed_title_ok", "outcome": "not_evaluated", "reason": "r"}]
        ),
    )

    assert verdict["is_acceptance_evidence"] is False
    assert EVIDENCE_GATE_NOT_EVALUATED in [r["code"] for r in verdict["refusals"]]


def test_an_excluded_gate_does_not_disturb_an_otherwise_good_run() -> None:
    verdict = acceptance_evidence_verdict(
        run=_GOOD_RUN,
        execution_mode="live",
        evidence_bundle=bundle(
            gate_coverage=[{"gate": "title_ok", "outcome": "excluded", "reason": "r"}]
        ),
    )

    assert verdict["is_acceptance_evidence"] is True
    assert verdict["refusals"] == []


def test_the_flip_guard_inherits_the_rule_without_re_deriving_it() -> None:
    # The rule lives in `gate_coverage_verdict` alone. `flip_refusals` never reads a
    # gate list; it refuses because the acceptance verdict already did.
    template = {
        "provider": "lexfind",
        "code_key": "live",
        "config_key": "never_turned",
        "agrees_with_server": True,
    }
    verdict = acceptance_evidence_verdict(
        run=_GOOD_RUN,
        execution_mode="live",
        evidence_bundle=bundle(
            gate_coverage=[{"gate": "indexed_title_ok", "outcome": "not_evaluated", "reason": "r"}]
        ),
    )

    codes = [
        r["code"]
        for r in flip_refusals(
            template=template,
            desired_enabled=True,
            evidence_verdict=verdict,
            evidence_provider="lexfind",
        )
    ]

    assert "evidence_run_is_not_acceptance_evidence" in codes


def test_the_same_run_with_only_excluded_gates_is_flippable() -> None:
    template = {
        "provider": "lexfind",
        "code_key": "live",
        "config_key": "never_turned",
        "agrees_with_server": True,
    }
    verdict = acceptance_evidence_verdict(
        run=_GOOD_RUN,
        execution_mode="live",
        evidence_bundle=bundle(
            gate_coverage=[{"gate": "title_ok", "outcome": "excluded", "reason": "r"}]
        ),
    )

    assert (
        flip_refusals(
            template=template,
            desired_enabled=True,
            evidence_verdict=verdict,
            evidence_provider="lexfind",
        )
        == []
    )
