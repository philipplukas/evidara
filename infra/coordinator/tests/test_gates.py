"""Tests for the human gate configuration and evaluation logic."""

from __future__ import annotations

from datetime import timedelta
from pathlib import Path
from textwrap import dedent

import pytest

from coordinator.gates import (
    GateDefinition,
    GateRegistry,
    _evaluate_auto_approve,
    _parse_duration,
    load_gate_config,
)


class TestParseDuration:
    def test_hours(self):
        assert _parse_duration("4h") == timedelta(hours=4)

    def test_minutes(self):
        assert _parse_duration("30m") == timedelta(minutes=30)

    def test_days(self):
        assert _parse_duration("1d") == timedelta(days=1)

    def test_bare_number_is_hours(self):
        assert _parse_duration("2") == timedelta(hours=2)


class TestAutoApprove:
    def test_never_returns_false(self):
        assert _evaluate_auto_approve("never", {}) is False

    def test_ci_green_true(self):
        assert _evaluate_auto_approve("ci_green", {"ci_green": True}) is True

    def test_ci_green_false(self):
        assert _evaluate_auto_approve("ci_green", {"ci_green": False}) is False

    def test_estimated_cost_under(self):
        assert _evaluate_auto_approve("estimated_cost < 5", {"estimated_cost": 3}) is True

    def test_estimated_cost_over(self):
        assert _evaluate_auto_approve("estimated_cost < 5", {"estimated_cost": 10}) is False

    def test_compound_and(self):
        ctx = {"ci_green": True, "estimated_cost": 2}
        assert _evaluate_auto_approve("ci_green AND estimated_cost < 5", ctx) is True

    def test_compound_and_partial_fail(self):
        ctx = {"ci_green": False, "estimated_cost": 2}
        assert _evaluate_auto_approve("ci_green AND estimated_cost < 5", ctx) is False

    def test_unknown_expression_is_false(self):
        assert _evaluate_auto_approve("some_future_condition", {}) is False

    def test_staging_deploy_age(self):
        ctx = {"last_staging_deploy_age_hours": 3}
        assert _evaluate_auto_approve("last_staging_deploy_age > 1h", ctx) is True

    def test_staging_deploy_age_too_recent(self):
        ctx = {"last_staging_deploy_age_hours": 0.5}
        assert _evaluate_auto_approve("last_staging_deploy_age > 1h", ctx) is False


class TestGateRegistry:
    def test_requires_approval_for_never_gate(self):
        gate = GateDefinition(
            name="prod", channel="#approvals", timeout=timedelta(hours=24), auto_approve="never"
        )
        registry = GateRegistry(gates={"prod": gate})
        assert registry.requires_approval("prod", {}) is True

    def test_does_not_require_approval_when_auto_approve_passes(self):
        gate = GateDefinition(
            name="staging", channel="#approvals", timeout=timedelta(hours=2), auto_approve="ci_green"
        )
        registry = GateRegistry(gates={"staging": gate})
        assert registry.requires_approval("staging", {"ci_green": True}) is False

    def test_unknown_gate_does_not_require_approval(self):
        registry = GateRegistry()
        assert registry.requires_approval("nonexistent", {}) is False


class TestLoadGateConfig:
    def test_loads_yaml(self, tmp_path: Path):
        config = tmp_path / "gates.yaml"
        config.write_text(dedent("""\
            gates:
              deploy_prod:
                channel: "#prod-approvals"
                timeout: "24h"
                auto_approve: "never"
                fallback: "reject"
              merge:
                channel: "#dev"
                timeout: "4h"
                auto_approve: "ci_green"
                fallback: "hold"
        """))
        registry = load_gate_config(config)
        assert len(registry.gates) == 2
        prod = registry.get("deploy_prod")
        assert prod is not None
        assert prod.timeout == timedelta(hours=24)
        assert prod.auto_approve == "never"
        assert prod.fallback == "reject"

        merge = registry.get("merge")
        assert merge is not None
        assert merge.auto_approve == "ci_green"
        assert merge.fallback == "hold"
