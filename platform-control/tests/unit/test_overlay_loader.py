"""Unit tests for platform_control.overlays.loader.

WHY THESE TESTS EXIST:
- The loader defines the merge protocol between shared defaults and
  per-country overrides. Getting it wrong silently changes what text
  operators and users see.
- `{country_code}` substitution is the only templating we support;
  future consumers must trust that behaviour.

WHAT WE DON'T TEST:
- YAML parsing itself (pyyaml is a dependency).
- The actual shipped overlay content (covered by
  scripts/check_country_overlay_files.py against the real files).
"""

from __future__ import annotations

from pathlib import Path

import pytest
import yaml

from platform_control.overlays.loader import (
    OverlayLoadError,
    _deep_merge,
    _substitute_country_code,
    load_operator_content,
    load_user_content,
)


def _write_yaml(path: Path, payload: dict) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(yaml.safe_dump(payload, sort_keys=False), encoding="utf-8")


class TestDeepMerge:
    def test_scalar_override_replaces_base(self) -> None:
        assert _deep_merge({"a": 1}, {"a": 2}) == {"a": 2}

    def test_base_key_preserved_when_not_overridden(self) -> None:
        assert _deep_merge({"a": 1, "b": 2}, {"b": 20}) == {"a": 1, "b": 20}

    def test_nested_dict_recurses(self) -> None:
        base = {"triage": {"mapping": {"owner": "platform", "hint": "X"}}}
        override = {"triage": {"mapping": {"owner": "ops"}}}
        assert _deep_merge(base, override) == {"triage": {"mapping": {"owner": "ops", "hint": "X"}}}

    def test_list_replaces_wholesale(self) -> None:
        # Lists do NOT merge element-wise; a country must declare the full list.
        base = {"checklist": ["a", "b", "c"]}
        override = {"checklist": ["d"]}
        assert _deep_merge(base, override) == {"checklist": ["d"]}

    def test_dict_over_scalar_replaces(self) -> None:
        assert _deep_merge({"x": 1}, {"x": {"y": 2}}) == {"x": {"y": 2}}


class TestCountryCodeSubstitution:
    def test_substitutes_in_flat_string(self) -> None:
        assert _substitute_country_code("hello {country_code}", "CH") == "hello CH"

    def test_substitutes_in_nested_dict(self) -> None:
        payload = {"a": {"b": "x {country_code} y"}}
        assert _substitute_country_code(payload, "AT") == {"a": {"b": "x AT y"}}

    def test_substitutes_in_list(self) -> None:
        assert _substitute_country_code(["{country_code}", "plain"], "DE") == ["DE", "plain"]

    def test_leaves_non_strings_alone(self) -> None:
        assert _substitute_country_code({"n": 42, "b": True, "z": None}, "FR") == {
            "n": 42,
            "b": True,
            "z": None,
        }

    def test_only_replaces_literal_token(self) -> None:
        # Ensures we don't accidentally interpret {anything_else}.
        assert _substitute_country_code("{other}", "IT") == "{other}"


class TestLoadUserContent:
    def test_shared_default_applies_when_country_missing(self, tmp_path: Path) -> None:
        _write_yaml(
            tmp_path / "_shared" / "user-content.yaml",
            {"version": 1, "result_subtitle_pattern": {"template": "shared"}},
        )
        (tmp_path / "ch").mkdir()  # empty country dir
        merged = load_user_content("CH", tmp_path)
        assert merged["result_subtitle_pattern"]["template"] == "shared"

    def test_country_override_wins(self, tmp_path: Path) -> None:
        _write_yaml(
            tmp_path / "_shared" / "user-content.yaml",
            {"version": 1, "result_subtitle_pattern": {"template": "shared"}},
        )
        _write_yaml(
            tmp_path / "ch" / "user-content.yaml",
            {
                "version": 1,
                "country_code": "CH",
                "result_subtitle_pattern": {"template": "ch-custom"},
            },
        )
        merged = load_user_content("CH", tmp_path)
        assert merged["result_subtitle_pattern"]["template"] == "ch-custom"

    def test_country_adds_new_field(self, tmp_path: Path) -> None:
        _write_yaml(
            tmp_path / "_shared" / "user-content.yaml",
            {"version": 1, "result_subtitle_pattern": {"template": "X"}},
        )
        _write_yaml(
            tmp_path / "at" / "user-content.yaml",
            {
                "version": 1,
                "country_code": "AT",
                "filters": {"jurisdiction": {"label": "Austrian"}},
            },
        )
        merged = load_user_content("AT", tmp_path)
        assert merged["result_subtitle_pattern"]["template"] == "X"
        assert merged["filters"]["jurisdiction"]["label"] == "Austrian"

    def test_missing_country_dir_raises(self, tmp_path: Path) -> None:
        _write_yaml(
            tmp_path / "_shared" / "user-content.yaml",
            {"version": 1},
        )
        with pytest.raises(OverlayLoadError, match="Country overlay directory missing"):
            load_user_content("XX", tmp_path)


class TestLoadOperatorContent:
    def test_country_code_substituted_in_shared_strings(self, tmp_path: Path) -> None:
        _write_yaml(
            tmp_path / "_shared" / "operator-content.yaml",
            {
                "version": 1,
                "triage_overlays": {
                    "mapping_drift": {
                        "first_action": "Check canonical {country_code} mapping.",
                        "escalation_owner": "platform-control",
                    }
                },
            },
        )
        (tmp_path / "fr").mkdir()
        merged = load_operator_content("FR", tmp_path)
        assert (
            merged["triage_overlays"]["mapping_drift"]["first_action"]
            == "Check canonical FR mapping."
        )
        assert merged["triage_overlays"]["mapping_drift"]["escalation_owner"] == "platform-control"

    def test_country_override_does_not_re_substitute(self, tmp_path: Path) -> None:
        # If a country writes a literal "{country_code}" placeholder, it
        # still gets substituted. That is the documented behaviour.
        _write_yaml(tmp_path / "_shared" / "operator-content.yaml", {"version": 1})
        _write_yaml(
            tmp_path / "it" / "operator-content.yaml",
            {
                "version": 1,
                "country_code": "IT",
                "status_note": "Scaffold for {country_code}",
            },
        )
        merged = load_operator_content("IT", tmp_path)
        assert merged["status_note"] == "Scaffold for IT"

    def test_shared_list_is_replaced_when_country_overrides(self, tmp_path: Path) -> None:
        _write_yaml(
            tmp_path / "_shared" / "operator-content.yaml",
            {"version": 1, "approval_hotspots": ["shared-a", "shared-b"]},
        )
        _write_yaml(
            tmp_path / "de" / "operator-content.yaml",
            {"version": 1, "country_code": "DE", "approval_hotspots": ["de-specific"]},
        )
        merged = load_operator_content("DE", tmp_path)
        assert merged["approval_hotspots"] == ["de-specific"]
