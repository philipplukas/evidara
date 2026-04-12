"""Human gate configuration and evaluation.

Gates define async approval checkpoints in autonomous workflows.  Each gate
posts a Slack message with approve/reject buttons and waits for a Temporal
signal (or timeout).
"""

from __future__ import annotations

from dataclasses import dataclass, field
from datetime import timedelta
from pathlib import Path
from typing import Literal

import yaml


@dataclass(frozen=True)
class GateDefinition:
    name: str
    channel: str
    timeout: timedelta
    auto_approve: str = "never"
    fallback: Literal["reject", "hold", "approve"] = "reject"


@dataclass
class GateRegistry:
    gates: dict[str, GateDefinition] = field(default_factory=dict)

    def get(self, name: str) -> GateDefinition | None:
        return self.gates.get(name)

    def requires_approval(self, name: str, context: dict[str, object]) -> bool:
        """Return True if the gate requires human approval given the context."""
        gate = self.gates.get(name)
        if gate is None:
            return False
        return not _evaluate_auto_approve(gate.auto_approve, context)


def load_gate_config(path: Path) -> GateRegistry:
    """Load gate definitions from a YAML file."""
    raw = yaml.safe_load(path.read_text(encoding="utf-8"))
    gates: dict[str, GateDefinition] = {}
    for name, spec in (raw.get("gates") or {}).items():
        gates[name] = GateDefinition(
            name=name,
            channel=spec["channel"],
            timeout=_parse_duration(spec.get("timeout", "4h")),
            auto_approve=spec.get("auto_approve", "never"),
            fallback=spec.get("fallback", "reject"),
        )
    return GateRegistry(gates=gates)


def _parse_duration(value: str) -> timedelta:
    """Parse a human-friendly duration like '4h', '30m', '24h' into a timedelta."""
    value = value.strip().lower()
    if value.endswith("h"):
        return timedelta(hours=float(value[:-1]))
    if value.endswith("m"):
        return timedelta(minutes=float(value[:-1]))
    if value.endswith("d"):
        return timedelta(days=float(value[:-1]))
    return timedelta(hours=float(value))


def _evaluate_auto_approve(expression: str, context: dict[str, object]) -> bool:
    """Evaluate a simple auto-approve expression against context.

    Supported atoms: 'never', 'ci_green', 'estimated_cost < N'.
    Compound: 'X AND Y'.  Unknown atoms evaluate to False (safe default).
    """
    expression = expression.strip()
    if expression == "never":
        return False

    if " AND " in expression:
        parts = expression.split(" AND ")
        return all(_evaluate_auto_approve(p.strip(), context) for p in parts)

    if expression == "ci_green":
        return bool(context.get("ci_green", False))

    if expression.startswith("estimated_cost"):
        try:
            threshold = float(expression.split("<")[1].strip().lstrip("$"))
            cost = float(context.get("estimated_cost", 999))
            return cost < threshold
        except (IndexError, ValueError):
            return False

    if expression.startswith("last_staging_deploy_age"):
        try:
            threshold_hours = float(expression.split(">")[1].strip().rstrip("h"))
            age_hours = float(context.get("last_staging_deploy_age_hours", 0))
            return age_hours > threshold_hours
        except (IndexError, ValueError):
            return False

    return False
