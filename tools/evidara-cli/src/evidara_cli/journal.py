"""In-process workflow run journal (Phase 1 / synchronous CLI flows).

The durable run journal lives in platform-control (see ADR-0022 Phase 2).  For
Phase 1 synchronous CLI-led workflows this module provides an in-memory model
that assembles step evidence within a single command invocation.  It is also
the canonical Python shape that mirrors the future platform-control journal API
once those endpoints are implemented.
"""

from __future__ import annotations

from dataclasses import dataclass, field
from datetime import UTC, datetime
from typing import Any


@dataclass
class WorkflowRun:
    """Top-level record for a workflow execution."""

    run_id: str
    workflow: str
    requested_by: str
    status: str  # running | passed | failed | compensated | cancelled
    started_at: str = field(default_factory=lambda: datetime.now(UTC).isoformat())
    finished_at: str | None = None
    checkpoint: str | None = None
    approval_state: str = "not_required"  # not_required | pending | approved | rejected
    inputs: dict[str, Any] = field(default_factory=dict)


@dataclass
class WorkflowStepRun:
    """Record for a single step within a workflow run."""

    run_id: str
    step: str
    attempt: int
    side_effect_level: str  # none | reversible | irreversible
    status: str  # passed | failed_retriable | failed_terminal | needs_human | compensated
    inputs: dict[str, Any] = field(default_factory=dict)
    artifacts: dict[str, Any] = field(default_factory=dict)
    evidence: list[dict[str, Any]] = field(default_factory=list)
    correlation_id: str | None = None
    started_at: str = field(default_factory=lambda: datetime.now(UTC).isoformat())
    finished_at: str | None = None


class LocalJournal:
    """In-process workflow run journal for Phase 1 synchronous CLI-led workflows.

    Workflow state is ephemeral within a single process.  Operators can capture
    the envelope output of each command and replay or inspect it independently.
    Phase 2 will move durable state to platform-control.
    """

    def __init__(self) -> None:
        self._runs: dict[str, WorkflowRun] = {}
        self._steps: list[WorkflowStepRun] = []

    def create_run(
        self,
        run_id: str,
        workflow: str,
        *,
        requested_by: str = "cli",
        inputs: dict[str, Any] | None = None,
    ) -> WorkflowRun:
        """Register a new workflow run."""
        run = WorkflowRun(
            run_id=run_id,
            workflow=workflow,
            requested_by=requested_by,
            status="running",
            inputs=inputs or {},
        )
        self._runs[run_id] = run
        return run

    def record_step(self, step_run: WorkflowStepRun) -> None:
        """Append a completed step record."""
        step_run.finished_at = datetime.now(UTC).isoformat()
        self._steps.append(step_run)

    def get_run(self, run_id: str) -> WorkflowRun | None:
        return self._runs.get(run_id)

    def get_steps(self, run_id: str) -> list[WorkflowStepRun]:
        return [s for s in self._steps if s.run_id == run_id]

    def complete_run(
        self,
        run_id: str,
        *,
        status: str,
        checkpoint: str | None = None,
    ) -> None:
        """Mark a run finished."""
        run = self._runs.get(run_id)
        if run:
            run.status = status
            run.finished_at = datetime.now(UTC).isoformat()
            if checkpoint:
                run.checkpoint = checkpoint

    def to_evidence_summary(self, run_id: str) -> dict[str, Any]:
        """Produce a compact evidence summary for the given run."""
        run = self._runs.get(run_id)
        steps = self.get_steps(run_id)
        return {
            "run_id": run_id,
            "workflow": run.workflow if run else "unknown",
            "status": run.status if run else "unknown",
            "requested_by": run.requested_by if run else "unknown",
            "started_at": run.started_at if run else None,
            "finished_at": run.finished_at if run else None,
            "checkpoint": run.checkpoint if run else None,
            "step_count": len(steps),
            "steps": [
                {
                    "step": s.step,
                    "status": s.status,
                    "side_effect_level": s.side_effect_level,
                    "attempt": s.attempt,
                    "evidence_count": len(s.evidence),
                    "started_at": s.started_at,
                    "finished_at": s.finished_at,
                }
                for s in steps
            ],
        }
