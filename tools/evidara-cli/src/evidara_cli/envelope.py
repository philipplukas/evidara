"""Command envelope schema for agentic CLI workflow steps (ADR-0022).

Every workflow command returns a StepEnvelope so agents and operators receive
consistent, machine-readable feedback after each step.
"""

from __future__ import annotations

from dataclasses import asdict, dataclass, field
from typing import Any, Literal

# Stable string literals for step status and side-effect level.
StepStatus = Literal[
    "passed",
    "failed_retriable",
    "failed_terminal",
    "needs_human",
    "compensated",
]
SideEffectLevel = Literal["none", "reversible", "irreversible"]


@dataclass
class EvidenceItem:
    """A single supporting fact captured during a workflow step."""

    kind: str  # "http", "contract", "artifact", "count"
    target: str
    status_code: int | None = None
    detail: str | None = None

    def to_dict(self) -> dict[str, Any]:
        return {k: v for k, v in asdict(self).items() if v is not None}


@dataclass
class StepDecision:
    """Evaluator recommendation produced after a step completes."""

    recommended_action: str
    reason: str


@dataclass
class CompensationRef:
    """Recovery metadata for a reversible step."""

    available: bool
    command: str | None = None
    run_id: str | None = None

    def to_dict(self) -> dict[str, Any]:
        return {k: v for k, v in asdict(self).items() if v is not None}


@dataclass
class StepEnvelope:
    """Consistent JSON envelope returned by every workflow step.

    Fields follow the contract defined in ADR-0022 and the agentic CLI workflow
    architecture document.
    """

    ok: bool
    workflow: str
    run_id: str
    step: str
    status: StepStatus
    side_effect_level: SideEffectLevel
    inputs: dict[str, Any] = field(default_factory=dict)
    artifacts: dict[str, Any] = field(default_factory=dict)
    evidence: list[EvidenceItem] = field(default_factory=list)
    decision: StepDecision | None = None
    next_actions: list[str] = field(default_factory=list)
    compensation: CompensationRef | None = None

    def to_dict(self) -> dict[str, Any]:
        return {
            "ok": self.ok,
            "workflow": self.workflow,
            "run_id": self.run_id,
            "step": self.step,
            "status": self.status,
            "side_effect_level": self.side_effect_level,
            "inputs": self.inputs,
            "artifacts": self.artifacts,
            "evidence": [e.to_dict() for e in self.evidence],
            "decision": asdict(self.decision) if self.decision else None,
            "next_actions": self.next_actions,
            "compensation": self.compensation.to_dict() if self.compensation else None,
        }
