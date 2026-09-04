from __future__ import annotations

import json
from pathlib import Path

from platform_control.domain import WizardRunState

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


def test_spec_states_are_exactly_the_states_the_code_can_persist() -> None:
    """The spec and `WizardRunState` must not drift apart (#560).

    Adding an enum member without a transition — or a transition to a state the
    code cannot store — is how a state machine ends up with members nothing ever
    reaches. `GateExpired` is the first state added since the wizard was written,
    so this is the assertion that makes the next one carry its transitions too.
    """
    spec = _load_json(SPEC_PATH)
    assert set(spec["states"]) == {state.value for state in WizardRunState}


def test_terminal_states_are_declared_and_actually_terminal() -> None:
    """A terminal state exists, is reachable, and nothing leads out of it.

    `GateExpired` is where an un-actioned human gate lands. It must be a dead end:
    resuming an abandoned run means a new pilot, which is a new operator decision.
    """
    spec = _load_json(SPEC_PATH)
    states = set(spec["states"])
    terminal = set(spec["terminal_states"])

    assert terminal, "the wizard must have at least one terminal state (#560)"
    assert terminal <= states
    assert WizardRunState.GATE_EXPIRED.value in terminal

    for transition in spec["transitions"]:
        assert transition["from"] not in terminal, (
            f"{transition['from']} is declared terminal but has an outgoing "
            f"'{transition['event']}' transition."
        )

    incoming_to_expired = {
        (t["from"], t["event"])
        for t in spec["transitions"]
        if t["to"] == WizardRunState.GATE_EXPIRED.value
    }
    assert incoming_to_expired == {(WizardRunState.HUMAN_GATE_APPROVAL.value, "gate_expired")}, (
        "a run may only expire out of the human gate, and only by timing out"
    )


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
