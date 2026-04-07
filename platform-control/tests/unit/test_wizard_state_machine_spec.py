from __future__ import annotations

import json
from pathlib import Path

FIXTURES_DIR = Path(__file__).resolve().parents[1] / "fixtures"
SPEC_PATH = FIXTURES_DIR / "wizard_state_machine_spec.json"
SCENARIOS_PATH = FIXTURES_DIR / "wizard_battle_test_scenarios.json"


def _load_json(path: Path) -> dict:
    return json.loads(path.read_text(encoding="utf-8"))


def test_wizard_state_machine_transitions_are_consistent() -> None:
    spec = _load_json(SPEC_PATH)
    states = set(spec["states"])
    initial_state = spec["initial_state"]
    transitions = spec["transitions"]

    assert initial_state in states
    assert transitions

    seen_pairs: set[tuple[str, str]] = set()
    from_states = set()
    to_states = set()

    for transition in transitions:
        from_state = transition["from"]
        to_state = transition["to"]
        event = transition["event"]
        guard = transition["guard"]

        assert from_state in states
        assert to_state in states
        assert event
        assert guard

        pair = (from_state, event)
        assert pair not in seen_pairs
        seen_pairs.add(pair)
        from_states.add(from_state)
        to_states.add(to_state)

    # Every state should be reachable from the initial state, directly or indirectly.
    reachable = {initial_state}
    changed = True
    while changed:
        changed = False
        for transition in transitions:
            if transition["from"] in reachable and transition["to"] not in reachable:
                reachable.add(transition["to"])
                changed = True

    assert reachable == states
    # Every non-initial state should have at least one incoming transition.
    assert (states - {initial_state}).issubset(to_states)
    # Initial state should be able to leave.
    assert initial_state in from_states


def test_battle_test_scenarios_do_not_overload_states() -> None:
    thresholds_payload = _load_json(SCENARIOS_PATH)
    scenarios = thresholds_payload["scenarios"]
    thresholds = thresholds_payload["overload_thresholds"]

    for scenario in scenarios:
        for state_name, metrics in scenario["state_metrics"].items():
            assert state_name
            assert metrics["human_decisions"] <= thresholds["max_human_decisions_per_state"]
            assert metrics["error_classes"] <= thresholds["max_error_classes_per_state"]
            assert metrics["screens_per_decision"] <= thresholds["max_screens_per_decision"]
            assert (
                metrics["state_duration_skew_ratio_p95"]
                <= thresholds["max_state_duration_skew_ratio_p95"]
            )
