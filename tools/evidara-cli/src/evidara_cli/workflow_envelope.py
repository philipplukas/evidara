"""Command envelope schema for agentic CLI workflow steps.

Every workflow command returns a consistent JSON envelope defined here.
See ADR-0022 and docs/architecture/agentic-cli-workflow-architecture.md.
"""

from __future__ import annotations

from datetime import UTC, datetime
from typing import Any, Literal

SideEffectLevel = Literal["none", "reversible", "irreversible"]
StepStatus = Literal["passed", "failed_retriable", "failed_terminal", "needs_human", "compensated"]


def build_envelope(
    *,
    ok: bool,
    workflow: str,
    run_id: str,
    step: str,
    status: StepStatus,
    side_effect_level: SideEffectLevel,
    inputs: dict[str, Any] | None = None,
    artifacts: dict[str, Any] | None = None,
    evidence: list[dict[str, Any]] | None = None,
    decision: dict[str, Any] | None = None,
    next_actions: list[str] | None = None,
    compensation: dict[str, Any] | None = None,
) -> dict[str, Any]:
    """Assemble a workflow step envelope.

    Args:
        ok: Overall command success (False for transport, evaluation, or contract failures).
        workflow: Stable workflow family name, e.g. ``source-draft``.
        run_id: Durable workflow run identifier; stable across steps.
        step: Stable step identifier, e.g. ``source.inspect``.
        status: Step outcome classification.
        side_effect_level: Mutation class: ``none``, ``reversible``, or ``irreversible``.
        inputs: Minimal structured echo of inputs (no secrets, no oversized payloads).
        artifacts: Key IDs, counts, or refs produced by the step.
        evidence: Supporting facts for operator or evaluator review.
        decision: Recommended next action and rationale.
        next_actions: Enumerated safe continuations for bounded planner branching.
        compensation: Recovery metadata if available.

    Returns:
        Fully populated envelope dict suitable for JSON serialisation.
    """
    return {
        "ok": ok,
        "workflow": workflow,
        "run_id": run_id,
        "step": step,
        "status": status,
        "side_effect_level": side_effect_level,
        "inputs": inputs or {},
        "artifacts": artifacts or {},
        "evidence": evidence or [],
        "decision": decision or {},
        "next_actions": next_actions or [],
        "compensation": compensation if compensation is not None else {"available": False},
        "timestamp": datetime.now(UTC).isoformat(),
    }


def evidence_http(
    target: str,
    *,
    status_code: int,
    method: str = "GET",
    ok: bool | None = None,
) -> dict[str, Any]:
    """Build an HTTP evidence entry."""
    return {
        "kind": "http",
        "method": method,
        "target": target,
        "status_code": status_code,
        "ok": (status_code < 400) if ok is None else ok,
    }


def evidence_check(name: str, *, passed: bool, detail: str = "") -> dict[str, Any]:
    """Build a named rule-check evidence entry."""
    entry: dict[str, Any] = {"kind": "check", "name": name, "passed": passed}
    if detail:
        entry["detail"] = detail
    return entry


def compensation_command(run_id: str, workflow_prefix: str = "source") -> dict[str, Any]:
    """Build a compensation metadata block pointing to the CLI compensate command."""
    return {
        "available": True,
        "command": f"evidara workflow {workflow_prefix} compensate --run-id {run_id}",
    }
