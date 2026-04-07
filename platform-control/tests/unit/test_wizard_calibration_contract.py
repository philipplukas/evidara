from __future__ import annotations

import json
from pathlib import Path

from jsonschema import Draft202012Validator


def _repo_root() -> Path:
    return Path(__file__).resolve().parents[3]


def test_wizard_calibration_decision_log_example_matches_contract_schema() -> None:
    repo_root = _repo_root()
    schema_path = (
        repo_root / "contracts" / "schemas" / "wizard-calibration-decision-log.schema.json"
    )
    schema = json.loads(schema_path.read_text(encoding="utf-8"))
    example = json.loads(
        (
            repo_root
            / "platform-control"
            / "tests"
            / "fixtures"
            / "wizard_calibration_decision_log_example.json"
        ).read_text(encoding="utf-8")
    )

    Draft202012Validator(schema).validate(example)

    # Domain invariant: high threshold must remain above low threshold.
    new_cfg = example["new_configuration"]
    assert new_cfg["high_threshold"] > new_cfg["low_threshold"]
    assert (
        example["previous_configuration"]["high_threshold"]
        > example["previous_configuration"]["low_threshold"]
    )
