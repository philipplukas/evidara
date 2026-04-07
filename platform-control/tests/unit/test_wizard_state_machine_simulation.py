from __future__ import annotations

import json
from dataclasses import dataclass
from pathlib import Path

FIXTURES_DIR = Path(__file__).resolve().parents[1] / "fixtures"
OVERLOAD_EXAMPLES_PATH = FIXTURES_DIR / "wizard_battle_test_overload_examples.json"


@dataclass(frozen=True)
class SplitRecommendation:
    scenario_id: str
    state_name: str
    reason_code: str
    details: str


def _load_json(path: Path) -> dict:
    return json.loads(path.read_text(encoding="utf-8"))


def _build_recommendations(payload: dict) -> list[SplitRecommendation]:
    thresholds = payload["overload_thresholds"]
    recommendations: list[SplitRecommendation] = []

    for scenario in payload["scenarios"]:
        scenario_id = scenario["id"]
        for state_name, metrics in scenario["state_metrics"].items():
            if metrics["human_decisions"] > thresholds["max_human_decisions_per_state"]:
                recommendations.append(
                    SplitRecommendation(
                        scenario_id=scenario_id,
                        state_name=state_name,
                        reason_code="multiple_human_decisions",
                        details=(
                            f"human_decisions={metrics['human_decisions']} exceeds "
                            f"threshold={thresholds['max_human_decisions_per_state']}"
                        ),
                    )
                )
            if metrics["error_classes"] > thresholds["max_error_classes_per_state"]:
                recommendations.append(
                    SplitRecommendation(
                        scenario_id=scenario_id,
                        state_name=state_name,
                        reason_code="error_class_explosion",
                        details=(
                            f"error_classes={metrics['error_classes']} exceeds "
                            f"threshold={thresholds['max_error_classes_per_state']}"
                        ),
                    )
                )
            if metrics["screens_per_decision"] > thresholds["max_screens_per_decision"]:
                recommendations.append(
                    SplitRecommendation(
                        scenario_id=scenario_id,
                        state_name=state_name,
                        reason_code="operator_context_switch",
                        details=(
                            f"screens_per_decision={metrics['screens_per_decision']} exceeds "
                            f"threshold={thresholds['max_screens_per_decision']}"
                        ),
                    )
                )
            if (
                metrics["state_duration_skew_ratio_p95"]
                > thresholds["max_state_duration_skew_ratio_p95"]
            ):
                recommendations.append(
                    SplitRecommendation(
                        scenario_id=scenario_id,
                        state_name=state_name,
                        reason_code="duration_skew_hotspot",
                        details=(
                            f"state_duration_skew_ratio_p95="
                            f"{metrics['state_duration_skew_ratio_p95']} exceeds "
                            f"threshold={thresholds['max_state_duration_skew_ratio_p95']}"
                        ),
                    )
                )
    return recommendations


def test_simulation_generates_split_recommendations_for_overload_cases() -> None:
    payload = _load_json(OVERLOAD_EXAMPLES_PATH)
    recommendations = _build_recommendations(payload)

    reason_codes = {
        (item.scenario_id, item.state_name, item.reason_code) for item in recommendations
    }

    assert ("approval_overload", "HumanGateApproval", "multiple_human_decisions") in reason_codes
    assert ("approval_overload", "HumanGateApproval", "operator_context_switch") in reason_codes
    assert ("scaledrun_error_explosion", "ScaledRun", "error_class_explosion") in reason_codes
    assert ("scaledrun_error_explosion", "ScaledRun", "duration_skew_hotspot") in reason_codes


def test_simulation_reason_codes_are_actionable_and_documented() -> None:
    payload = _load_json(OVERLOAD_EXAMPLES_PATH)
    recommendations = _build_recommendations(payload)

    assert recommendations
    for recommendation in recommendations:
        assert recommendation.reason_code in {
            "multiple_human_decisions",
            "error_class_explosion",
            "operator_context_switch",
            "duration_skew_hotspot",
        }
        assert recommendation.details
