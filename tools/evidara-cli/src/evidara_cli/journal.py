"""Local workflow run journal for Phase 1 of ADR-0022.

The durable system of record is `platform-control`.  This module provides a
lightweight, file-backed journal kept at ``~/.evidara/journal/`` (or the path
in the ``EVIDARA_CLI_JOURNAL_DIR`` environment variable) for local debugging and
CLI-led synchronous workflows.

Structure on disk: one JSON file per run, named ``<run_id>.json``.
"""

from __future__ import annotations

import json
import os
import uuid
from dataclasses import asdict, dataclass, field
from datetime import UTC, datetime
from pathlib import Path
from typing import Any

_DEFAULT_JOURNAL_DIR = Path.home() / ".evidara" / "journal"


def _journal_dir() -> Path:
    env = os.environ.get("EVIDARA_CLI_JOURNAL_DIR", "").strip()
    return Path(env) if env else _DEFAULT_JOURNAL_DIR


@dataclass
class WorkflowStepRun:
    """Persisted record of a single step execution within a workflow run."""

    step: str
    attempt: int
    status: str
    side_effect_level: str
    started_at: str
    finished_at: str | None
    inputs: dict[str, Any]
    artifacts: dict[str, Any]
    evidence: list[dict[str, Any]]


@dataclass
class WorkflowRun:
    """Top-level workflow run record.

    ``status`` lifecycle: ``running`` → ``passed`` | ``failed`` | ``cancelled`` | ``compensated``
    ``checkpoint`` is updated to the last completed step name.
    """

    run_id: str
    workflow: str
    status: str
    started_at: str
    finished_at: str | None
    checkpoint: str | None
    inputs: dict[str, Any]
    steps: list[WorkflowStepRun] = field(default_factory=list)

    def to_dict(self) -> dict[str, Any]:
        return asdict(self)


def _now_iso() -> str:
    return datetime.now(UTC).isoformat()


class WorkflowJournal:
    """File-backed workflow journal for local CLI sessions.

    Each workflow run is stored as a single JSON file under *journal_dir*.
    """

    def __init__(self, journal_dir: Path | None = None) -> None:
        self._dir = journal_dir or _journal_dir()

    def _run_path(self, run_id: str) -> Path:
        return self._dir / f"{run_id}.json"

    # ------------------------------------------------------------------
    # Write helpers
    # ------------------------------------------------------------------

    def create_run(self, workflow: str, inputs: dict[str, Any]) -> WorkflowRun:
        """Create and persist a new workflow run, returning the run record."""
        self._dir.mkdir(parents=True, exist_ok=True)
        ts = datetime.now(UTC).strftime("%Y%m%dT%H%M%SZ")
        slug = workflow.replace("-", "").replace("_", "")[:12]
        run_id = f"wf_{ts}_{slug}_{uuid.uuid4().hex[:8]}"
        run = WorkflowRun(
            run_id=run_id,
            workflow=workflow,
            status="running",
            started_at=_now_iso(),
            finished_at=None,
            checkpoint=None,
            inputs=inputs,
        )
        self._write(run)
        return run

    def record_step(self, run_id: str, envelope: dict[str, Any]) -> WorkflowRun:
        """Append a completed step envelope to the run and update the checkpoint.

        *envelope* is the dict returned by :func:`evidara_cli.envelope.build_envelope`.
        """
        run = self.get_run(run_id)
        if run is None:
            raise ValueError(f"Workflow run not found: {run_id}")
        step = envelope["step"]
        attempt = sum(1 for s in run.steps if s.step == step) + 1
        evidence: list[dict[str, Any]] = envelope.get("evidence") or []
        step_run = WorkflowStepRun(
            step=step,
            attempt=attempt,
            status=envelope["status"],
            side_effect_level=envelope["side_effect_level"],
            started_at=_now_iso(),
            finished_at=_now_iso(),
            inputs=envelope.get("inputs") or {},
            artifacts=envelope.get("artifacts") or {},
            evidence=evidence,
        )
        run.steps.append(step_run)
        run.checkpoint = step
        self._write(run)
        return run

    def close_run(self, run_id: str, status: str) -> WorkflowRun:
        """Set the terminal status and finished_at timestamp of a run."""
        run = self.get_run(run_id)
        if run is None:
            raise ValueError(f"Workflow run not found: {run_id}")
        run.status = status
        run.finished_at = _now_iso()
        self._write(run)
        return run

    # ------------------------------------------------------------------
    # Read helpers
    # ------------------------------------------------------------------

    def get_run(self, run_id: str) -> WorkflowRun | None:
        """Return the run record or ``None`` if it does not exist."""
        path = self._run_path(run_id)
        if not path.exists():
            return None
        data: dict[str, Any] = json.loads(path.read_text())
        raw_steps = data.pop("steps", [])
        steps = [WorkflowStepRun(**s) for s in raw_steps]
        return WorkflowRun(steps=steps, **data)

    def list_runs(self, workflow: str | None = None) -> list[WorkflowRun]:
        """Return all persisted runs, optionally filtered by workflow name."""
        if not self._dir.exists():
            return []
        runs: list[WorkflowRun] = []
        for path in sorted(self._dir.glob("wf_*.json"), reverse=True):
            run = self.get_run(path.stem)
            if run is not None and (workflow is None or run.workflow == workflow):
                runs.append(run)
        return runs

    def last_step_artifact(self, run_id: str, step: str, key: str) -> Any:
        """Return a specific artifact value from the latest attempt of *step*."""
        run = self.get_run(run_id)
        if run is None:
            return None
        matching = [s for s in reversed(run.steps) if s.step == step]
        if not matching:
            return None
        return matching[0].artifacts.get(key)

    # ------------------------------------------------------------------
    # Internal
    # ------------------------------------------------------------------

    def _write(self, run: WorkflowRun) -> None:
        self._dir.mkdir(parents=True, exist_ok=True)
        self._run_path(run.run_id).write_text(
            json.dumps(run.to_dict(), indent=2, default=str)
        )
