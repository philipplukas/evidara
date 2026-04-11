from __future__ import annotations

import pytest

from evidara_cli.proposal import _rule_based_proposal, propose_source_spec


def test_rule_based_proposal_basic() -> None:
    spec = _rule_based_proposal("https://www.ris.bka.gv.at/Dokument.wxe?Abfrage=Vfgh", None)
    assert spec["seed_url"] == "https://www.ris.bka.gv.at/Dokument.wxe?Abfrage=Vfgh"
    assert "ris" in spec["name"]
    assert spec["acquisition_strategy"] == "crawl"
    assert "application/pdf" in spec["content_types"]
    assert spec["confidence"] == 0.7
    assert spec["requires_review"] is True
    assert spec["dspy_assisted"] is False


def test_rule_based_proposal_with_name_hint() -> None:
    spec = _rule_based_proposal("https://example.com/docs", "my-source")
    assert spec["name"] == "my-source"


def test_rule_based_proposal_name_derived_from_domain() -> None:
    spec = _rule_based_proposal("https://rechtsinformationssystem.at/", None)
    assert spec["name"] == "rechtsinformationssystem-at"


def test_rule_based_proposal_has_required_keys() -> None:
    spec = _rule_based_proposal("https://example.com", None)
    required_keys = (
        "name", "seed_url", "acquisition_strategy", "content_types",
        "confidence", "rationale", "requires_review", "dspy_assisted",
    )
    for key in required_keys:
        assert key in spec, f"Missing key: {key}"


def test_propose_source_spec_without_dspy(monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setenv("EVIDARA_DSPY_ENABLED", "0")
    spec = propose_source_spec("https://example.com/legal", "legal-source")
    assert spec["name"] == "legal-source"
    assert spec["dspy_assisted"] is False


def test_propose_source_spec_falls_back_without_env_var(monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.delenv("EVIDARA_DSPY_ENABLED", raising=False)
    spec = propose_source_spec("https://example.com")
    assert spec["dspy_assisted"] is False
    assert spec["requires_review"] is True


def test_propose_source_spec_dspy_disabled_env(monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setenv("EVIDARA_DSPY_ENABLED", "false")
    spec = propose_source_spec("https://example.com")
    assert spec["dspy_assisted"] is False
