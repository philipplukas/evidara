from __future__ import annotations

import json
from pathlib import Path

FIXTURES_DIR = Path(__file__).resolve().parents[1] / "fixtures"
COUNTRY_PROFILES_PATH = FIXTURES_DIR / "wizard_country_hierarchy_profiles.json"

RISK_SCORE = {"low": 0.2, "medium": 0.6, "high": 1.0}


def _load_profiles() -> dict:
    return json.loads(COUNTRY_PROFILES_PATH.read_text(encoding="utf-8"))


def _normalize_depth(depth: int) -> float:
    # Expected depth range for this rollout: 3..7
    return max(0.0, min(1.0, (depth - 3) / 4))


def _normalize_breadth(breadth: int) -> float:
    # Expected breadth range for this rollout: 5..30
    return max(0.0, min(1.0, (breadth - 5) / 25))


def _normalize_language_count(language_count: int) -> float:
    # 1 language is baseline, 4 languages treated as max complexity.
    return max(0.0, min(1.0, (language_count - 1) / 3))


def _complexity_score(country: dict, weights: dict) -> float:
    return (
        _normalize_depth(country["estimated_depth"]) * weights["depth"]
        + _normalize_breadth(country["estimated_authority_breadth"]) * weights["breadth"]
        + (1.0 if country["administrative_dual_track"] else 0.0) * weights["admin_dual_track"]
        + _normalize_language_count(country["language_count"]) * weights["language_count"]
        + RISK_SCORE[country["metadata_quality_risk"]] * weights["metadata_quality_risk"]
        + RISK_SCORE[country["taxonomy_drift_risk"]] * weights["taxonomy_drift_risk"]
    )


def _classify(score: float, thresholds: dict) -> str:
    if score <= thresholds["low_max"]:
        return "low"
    if score <= thresholds["medium_max"]:
        return "medium"
    return "high"


def _recommended_shard_strategy(country: dict, complexity_class: str) -> str:
    if complexity_class == "high":
        return "country_jurisdiction_authority"
    if country["administrative_dual_track"]:
        return "country_jurisdiction"
    return "country_only"


def test_country_profiles_are_complete_and_unique() -> None:
    payload = _load_profiles()
    countries = payload["countries"]

    assert len(countries) == 5
    seen_codes: set[str] = set()

    for country in countries:
        code = country["country_code"]
        assert code not in seen_codes
        seen_codes.add(code)

        assert country["estimated_depth"] >= 3
        assert country["estimated_authority_breadth"] >= 5
        assert country["language_count"] >= 1
        assert country["metadata_quality_risk"] in RISK_SCORE
        assert country["taxonomy_drift_risk"] in RISK_SCORE
        assert country["source_notes"]


def test_country_complexity_scoring_and_shard_recommendations() -> None:
    payload = _load_profiles()
    weights = payload["scoring_weights"]
    thresholds = payload["classification_thresholds"]

    classifications = {}
    strategies = {}

    for country in payload["countries"]:
        score = _complexity_score(country, weights)
        complexity_class = _classify(score, thresholds)
        strategy = _recommended_shard_strategy(country, complexity_class)
        classifications[country["country_code"]] = complexity_class
        strategies[country["country_code"]] = strategy

    # Expected higher-complexity profiles for this rollout.
    assert classifications["CH"] == "high"
    assert classifications["DE"] in {"medium", "high"}
    # IT has quality risk but not necessarily highest hierarchy complexity.
    assert classifications["IT"] in {"medium", "high"}

    # High complexity countries should use the most granular shard strategy.
    assert strategies["CH"] == "country_jurisdiction_authority"
    assert strategies["DE"] in {"country_jurisdiction", "country_jurisdiction_authority"}

    # All countries in this set should avoid country-only strategy due to dual-track structures.
    assert set(strategies.values()).issubset(
        {"country_jurisdiction", "country_jurisdiction_authority"}
    )
