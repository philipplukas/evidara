"""Workflow command envelope builder.

Constructs the standard JSON envelope returned by every evidara-cli workflow command as
defined by contracts/schemas/workflow-command-envelope.schema.json and ADR-0022.

This module is deliberately free of domain content and of imports beyond the standard
library, so that it can be reasoned about — and if wanted, lifted — on its own. That
boundary is enforced by tests/test_envelope.py, and the vocabulary (in particular what
``side_effect_level`` classifies) is documented in
docs/components/workflow-command-envelope.md.
"""

from __future__ import annotations

from typing import Any


def build_envelope(
    *,
    ok: bool,
    workflow: str,
    step: str,
    status: str,
    side_effect_level: str,
    inputs: dict[str, Any],
    run_id: str | None = None,
    artifacts: dict[str, Any] | None = None,
    evidence: list[dict[str, Any]] | None = None,
    decision: dict[str, Any] | None = None,
    next_actions: list[str] | None = None,
    compensation: dict[str, Any] | None = None,
    error: str | None = None,
    error_detail: dict[str, Any] | None = None,
) -> dict[str, Any]:
    """Build a standard workflow command envelope.

    Args:
        ok: Overall command success.
        workflow: Stable workflow family name (e.g. ``source-lifecycle``).
        step: Stable step identifier (e.g. ``source.inspect``).
        status: Step outcome: ``passed``, ``failed_retriable``, ``failed_terminal``,
            ``needs_human``, or ``compensated``.
        side_effect_level: Mutation class: ``none``, ``reversible``, or ``irreversible``.
        inputs: Minimal structured echo of command inputs.
        run_id: Optional durable run identifier.
        artifacts: Key ids, counts, or refs produced by the step.
        evidence: List of supporting facts for operator or evaluator review.
        decision: Recommended next action and rationale.
        next_actions: Enumerated safe continuations from this step.
        compensation: Recovery metadata if a compensating action is available.
        error: Error message when ``ok`` is ``False``.
        error_detail: Structured error detail for programmatic handling.

    Returns:
        A dict conforming to the WorkflowCommandEnvelope schema.
    """
    envelope: dict[str, Any] = {
        "ok": ok,
        "workflow": workflow,
        "run_id": run_id,
        "step": step,
        "status": status,
        "side_effect_level": side_effect_level,
        "inputs": inputs,
        "artifacts": artifacts,
        "evidence": evidence,
        "decision": decision,
        "next_actions": next_actions,
        "compensation": compensation,
    }
    if error is not None:
        envelope["error"] = error
    if error_detail is not None:
        envelope["error_detail"] = error_detail
    return envelope


def evidence_http(
    target: str,
    *,
    status_code: int,
    passed: bool | None = None,
    note: str | None = None,
) -> dict[str, Any]:
    """Build an HTTP evidence item."""
    item: dict[str, Any] = {
        "kind": "http",
        "target": target,
        "status_code": status_code,
        "passed": passed if passed is not None else (status_code < 400),
    }
    if note is not None:
        item["note"] = note
    return item


def evidence_assertion(
    target: str,
    *,
    value: Any,
    passed: bool,
    note: str | None = None,
) -> dict[str, Any]:
    """Build an assertion evidence item."""
    item: dict[str, Any] = {
        "kind": "assertion",
        "target": target,
        "value": value,
        "passed": passed,
    }
    if note is not None:
        item["note"] = note
    return item


def evidence_count(
    target: str,
    *,
    value: int,
    passed: bool,
    note: str | None = None,
) -> dict[str, Any]:
    """Build a count evidence item."""
    item: dict[str, Any] = {
        "kind": "count",
        "target": target,
        "value": value,
        "passed": passed,
    }
    if note is not None:
        item["note"] = note
    return item
