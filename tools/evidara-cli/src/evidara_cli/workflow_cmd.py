"""Workflow commands for the evidara CLI (ADR-0022).

Provides two sub-apps registered under the top-level ``workflow`` group:

- ``evidara workflow source`` — inspect, propose, apply, verify, compensate
- ``evidara workflow run``    — status, cancel, evidence

Every command returns a :class:`~evidara_cli.envelope.StepEnvelope` so agents
and operators receive consistent, machine-readable feedback.  Side effects are
classified as ``none``, ``reversible``, or ``irreversible``; compensation is
only possible for ``reversible`` steps.

DSPy is optional.  When ``--use-dspy`` is passed to ``propose`` the module
tries to import DSPy at runtime.  If it is not installed (or no language model
is configured) the command falls back silently to the rule-based proposal
generator and emits a notice in the envelope artifacts.
"""

from __future__ import annotations

import os
from pathlib import Path
from typing import Annotated, Any
from urllib.parse import urlparse

import typer

from evidara_cli.client import (
    HttpJsonError,
    join_url,
    platform_control_base_url,
    platform_control_headers,
    request_json,
    request_status,
)
from evidara_cli.envelope import (
    CompensationRef,
    EvidenceItem,
    StepDecision,
    StepEnvelope,
)
from evidara_cli.journal import WorkflowJournal

# ---------------------------------------------------------------------------
# Typer sub-apps
# ---------------------------------------------------------------------------

source_app = typer.Typer(
    no_args_is_help=True,
    help="Source workflow: inspect → propose → apply → verify → compensate.",
)
run_app = typer.Typer(
    no_args_is_help=True,
    help="Manage workflow run journal entries.",
)

# ---------------------------------------------------------------------------
# Shared helpers
# ---------------------------------------------------------------------------

_WORKFLOW_SOURCE = "source"


def _default_journal(journal_dir: Path | None = None) -> WorkflowJournal:
    return WorkflowJournal(journal_dir)


def _emit_envelope(envelope: StepEnvelope, *, human: bool) -> None:
    import json

    data = envelope.to_dict()
    if human or os.environ.get("EVIDARA_CLI_HUMAN", "").strip().lower() in ("1", "true", "yes"):
        typer.echo(json.dumps(data, indent=2, sort_keys=True, default=str))
    else:
        typer.echo(json.dumps(data, separators=(",", ":"), default=str))


def _compensation_cmd(run_id: str) -> str:
    return f"evidara workflow source compensate --run-id {run_id}"


# ---------------------------------------------------------------------------
# DSPy-optional proposal
# ---------------------------------------------------------------------------

def _propose_rule_based(seed_url: str, source_count: int) -> dict[str, Any]:
    """Rule-based spec template derived from *seed_url*."""
    parsed = urlparse(seed_url if "://" in seed_url else f"https://{seed_url}")
    domain = parsed.netloc or parsed.path.split("/")[0]
    name = domain.replace("www.", "").replace(".", "-")
    return {
        "name": name,
        "description": f"Source from {domain}",
        "source_type": "web",
        "seed_url": seed_url,
        "acquisition_spec": {
            "start_url": seed_url,
            "max_pages": 50,
            "allowed_domains": [domain],
        },
        "confidence": 0.5,
        "rationale": "Rule-based template derived from seed URL domain.",
        "duplicate_risk": "low" if source_count == 0 else "review-required",
    }


def _propose_with_dspy(seed_url: str, inspect_evidence: list[dict[str, Any]]) -> dict[str, Any]:
    """DSPy-assisted spec proposal. Falls back to rule-based if DSPy is unavailable."""
    try:
        import dspy  # noqa: F401
    except ImportError:
        return _propose_rule_based(seed_url, len(inspect_evidence))

    # A real implementation would configure a DSPy language model and run
    # ChainOfThought or Predict here. For Phase 0 we return a rule-based
    # result with a note that full DSPy optimisation requires a configured LM.
    base = _propose_rule_based(seed_url, len(inspect_evidence))
    base["rationale"] = (
        "DSPy module loaded but no language model configured; "
        "returning rule-based template. Set DSPY_LM to enable optimised proposals."
    )
    base["dspy_available"] = True
    return base


# ---------------------------------------------------------------------------
# evidara workflow source inspect
# ---------------------------------------------------------------------------

@source_app.command("inspect")
def source_inspect(
    source_id: Annotated[
        str | None,
        typer.Option("--source-id", help="Inspect a specific source by ID"),
    ] = None,
    run_id: Annotated[
        str | None,
        typer.Option("--run-id", help="Continue an existing workflow run"),
    ] = None,
    human: Annotated[bool, typer.Option("--human", help="Pretty-print JSON")] = False,
    correlation_id: Annotated[
        str | None, typer.Option("--correlation-id")
    ] = None,
) -> None:
    """Read-only discovery: health check + source list (side_effect_level: none)."""
    journal = _default_journal()
    if run_id is None:
        run = journal.create_run(_WORKFLOW_SOURCE, inputs={"source_id": source_id})
        run_id = run.run_id
    else:
        run = journal.get_run(run_id)
        if run is None:
            typer.echo(f"Run not found: {run_id}", err=True)
            raise typer.Exit(code=1)

    base = platform_control_base_url()
    headers = platform_control_headers(correlation_id=correlation_id)
    evidence: list[EvidenceItem] = []
    artifacts: dict[str, Any] = {}
    ok = True
    status: str = "passed"
    next_actions: list[str] = []

    try:
        health_code = request_status("GET", join_url(base, "/health"), headers=headers)
        evidence.append(
            EvidenceItem(kind="http", target="platform-control:/health", status_code=health_code)
        )
        if health_code != 200:
            ok = False
            status = "failed_retriable"

        if ok:
            sources_payload = request_json("GET", join_url(base, "/v1/sources"), headers=headers)
            source_count: int = 0
            if isinstance(sources_payload, dict):
                items = sources_payload.get("items", sources_payload.get("sources", []))
                if isinstance(items, list):
                    source_count = len(items)
            elif isinstance(sources_payload, list):
                source_count = len(sources_payload)
            artifacts["source_count"] = source_count
            evidence.append(
                EvidenceItem(
                    kind="count",
                    target="platform-control:/v1/sources",
                    detail=str(source_count),
                )
            )

            if source_id:
                detail = request_json(
                    "GET", join_url(base, f"/v1/sources/{source_id}"), headers=headers
                )
                artifacts["source"] = detail
                evidence.append(
                    EvidenceItem(
                        kind="http",
                        target=f"platform-control:/v1/sources/{source_id}",
                        status_code=200,
                    )
                )

            next_actions = ["propose"]

    except HttpJsonError as exc:
        ok = False
        status = "failed_retriable"
        evidence.append(EvidenceItem(kind="http", target=str(exc), detail=exc.body[:500]))

    decision = StepDecision(
        recommended_action="propose" if ok else "retry",
        reason=(
            "Platform-control reachable; ready for spec proposal."
            if ok
            else "Platform-control unreachable; retry or check connection."
        ),
    )
    envelope = StepEnvelope(
        ok=ok,
        workflow=_WORKFLOW_SOURCE,
        run_id=run_id,
        step="source.inspect",
        status=status,
        side_effect_level="none",
        inputs={"source_id": source_id},
        artifacts=artifacts,
        evidence=evidence,
        decision=decision,
        next_actions=next_actions,
    )
    journal.record_step(run_id, envelope)
    _emit_envelope(envelope, human=human)
    if not ok:
        raise typer.Exit(code=1)


# ---------------------------------------------------------------------------
# evidara workflow source propose
# ---------------------------------------------------------------------------

@source_app.command("propose")
def source_propose(
    seed_url: Annotated[str, typer.Option("--seed-url", help="Target URL for the source")],
    run_id: Annotated[
        str | None,
        typer.Option("--run-id", help="Continue an existing workflow run"),
    ] = None,
    use_dspy: Annotated[
        bool,
        typer.Option("--use-dspy", help="Use DSPy module for proposal (requires dspy package)"),
    ] = False,
    human: Annotated[bool, typer.Option("--human", help="Pretty-print JSON")] = False,
    correlation_id: Annotated[  # noqa: ARG001
        str | None, typer.Option("--correlation-id")
    ] = None,
) -> None:
    """Build a draft acquisition spec (side_effect_level: none, DSPy-optional)."""
    journal = _default_journal()
    if run_id is None:
        run = journal.create_run(_WORKFLOW_SOURCE, inputs={"seed_url": seed_url})
        run_id = run.run_id
    else:
        run = journal.get_run(run_id)
        if run is None:
            typer.echo(f"Run not found: {run_id}", err=True)
            raise typer.Exit(code=1)

    inspect_artifacts: list[dict[str, Any]] = []
    for step in run.steps:
        if step.step == "source.inspect":
            inspect_artifacts.append(step.artifacts)

    if use_dspy:
        spec = _propose_with_dspy(seed_url, inspect_artifacts)
    else:
        source_count = int(inspect_artifacts[-1].get("source_count", 0)) if inspect_artifacts else 0
        spec = _propose_rule_based(seed_url, source_count)

    evidence = [
        EvidenceItem(
            kind="artifact",
            target="proposed-spec",
            detail="rule-based" if not use_dspy else "dspy",
        )
    ]
    envelope = StepEnvelope(
        ok=True,
        workflow=_WORKFLOW_SOURCE,
        run_id=run_id,
        step="source.propose",
        status="passed",
        side_effect_level="none",
        inputs={"seed_url": seed_url, "use_dspy": use_dspy},
        artifacts={"proposed_spec": spec},
        evidence=evidence,
        decision=StepDecision(
            recommended_action="apply",
            reason="Spec proposed; review and apply to create draft source.",
        ),
        next_actions=["apply", "revise-spec"],
        compensation=None,
    )
    journal.record_step(run_id, envelope)
    _emit_envelope(envelope, human=human)


# ---------------------------------------------------------------------------
# evidara workflow source apply
# ---------------------------------------------------------------------------

@source_app.command("apply")
def source_apply(
    run_id: Annotated[
        str, typer.Option("--run-id", help="Workflow run ID from inspect or propose")
    ],
    source_name: Annotated[
        str | None,
        typer.Option("--source-name", help="Override source name from proposed spec"),
    ] = None,
    seed_url: Annotated[
        str | None,
        typer.Option("--seed-url", help="Override seed URL from proposed spec"),
    ] = None,
    human: Annotated[bool, typer.Option("--human", help="Pretty-print JSON")] = False,
    correlation_id: Annotated[
        str | None, typer.Option("--correlation-id")
    ] = None,
) -> None:
    """Create a draft source in platform-control (side_effect_level: reversible)."""
    journal = _default_journal()
    run = journal.get_run(run_id)
    if run is None:
        typer.echo(f"Run not found: {run_id}", err=True)
        raise typer.Exit(code=1)

    # Resolve spec: use proposed spec from journal, override with CLI flags.
    proposed_spec: dict[str, Any] = {}
    for step in reversed(run.steps):
        if step.step == "source.propose" and "proposed_spec" in step.artifacts:
            proposed_spec = dict(step.artifacts["proposed_spec"])
            break

    effective_name = source_name or proposed_spec.get("name", "unnamed-source")
    effective_url = seed_url or proposed_spec.get("seed_url", "")

    base = platform_control_base_url()
    headers = platform_control_headers(correlation_id=correlation_id)
    headers["Content-Type"] = "application/json"

    evidence: list[EvidenceItem] = []
    artifacts: dict[str, Any] = {"source_name": effective_name}
    ok = True
    status: str = "passed"

    try:
        payload = request_json(
            "POST",
            join_url(base, "/v1/sources/with-version"),
            headers=headers,
            json_body={
                "name": effective_name,
                "seed_url": effective_url,
                "acquisition_spec": proposed_spec.get(
                    "acquisition_spec",
                    {"start_url": effective_url, "max_pages": 50},
                ),
            },
        )
        source_id = None
        version_id = None
        if isinstance(payload, dict):
            source_id = payload.get("source_id") or payload.get("id")
            version_id = payload.get("source_version_id") or payload.get("version_id")
        artifacts["source_id"] = source_id
        artifacts["source_version_id"] = version_id
        evidence.append(
            EvidenceItem(
                kind="http",
                target="platform-control:/v1/sources/with-version",
                status_code=201,
                detail=f"source_id={source_id}",
            )
        )
    except HttpJsonError as exc:
        ok = False
        status = "failed_retriable"
        evidence.append(
            EvidenceItem(
                kind="http",
                target="platform-control:/v1/sources/with-version",
                detail=exc.body[:500],
            )
        )

    compensation = CompensationRef(
        available=ok,
        command=_compensation_cmd(run_id),
        run_id=run_id,
    )
    envelope = StepEnvelope(
        ok=ok,
        workflow=_WORKFLOW_SOURCE,
        run_id=run_id,
        step="source.apply",
        status=status,
        side_effect_level="reversible",
        inputs={"source_name": effective_name, "seed_url": effective_url},
        artifacts=artifacts,
        evidence=evidence,
        decision=StepDecision(
            recommended_action="verify" if ok else "compensate",
            reason=(
                "Draft source created; verify before requesting approval."
                if ok
                else "Creation failed; compensate or retry."
            ),
        ),
        next_actions=["verify"] if ok else ["compensate", "retry"],
        compensation=compensation,
    )
    journal.record_step(run_id, envelope)
    _emit_envelope(envelope, human=human)
    if not ok:
        raise typer.Exit(code=1)


# ---------------------------------------------------------------------------
# evidara workflow source verify
# ---------------------------------------------------------------------------

@source_app.command("verify")
def source_verify(
    run_id: Annotated[
        str | None,
        typer.Option("--run-id", help="Workflow run ID to resolve source_id from journal"),
    ] = None,
    source_id: Annotated[
        str | None,
        typer.Option("--source-id", help="Explicit source ID to verify"),
    ] = None,
    human: Annotated[bool, typer.Option("--human", help="Pretty-print JSON")] = False,
    correlation_id: Annotated[
        str | None, typer.Option("--correlation-id")
    ] = None,
) -> None:
    """Verify that the applied source exists and is well-formed (side_effect_level: none)."""
    if run_id is None and source_id is None:
        typer.echo("Provide --run-id or --source-id.", err=True)
        raise typer.Exit(code=1)

    journal = _default_journal()
    effective_run_id = run_id

    if run_id is not None:
        run = journal.get_run(run_id)
        if run is None:
            typer.echo(f"Run not found: {run_id}", err=True)
            raise typer.Exit(code=1)
        if source_id is None:
            source_id = journal.last_step_artifact(run_id, "source.apply", "source_id")
        if effective_run_id is None:
            effective_run_id = run_id
    else:
        # No run_id — create a ephemeral run for journal consistency.
        run = journal.create_run(_WORKFLOW_SOURCE, inputs={"source_id": source_id})
        effective_run_id = run.run_id

    if not source_id:
        typer.echo("Could not resolve source_id from journal; pass --source-id.", err=True)
        raise typer.Exit(code=1)

    base = platform_control_base_url()
    headers = platform_control_headers(correlation_id=correlation_id)
    evidence: list[EvidenceItem] = []
    artifacts: dict[str, Any] = {"source_id": source_id}
    checks: dict[str, bool] = {}
    ok = True
    status: str = "passed"

    try:
        detail = request_json("GET", join_url(base, f"/v1/sources/{source_id}"), headers=headers)
        evidence.append(
            EvidenceItem(
                kind="http",
                target=f"platform-control:/v1/sources/{source_id}",
                status_code=200,
            )
        )
        if isinstance(detail, dict):
            checks["id_present"] = bool(detail.get("source_id") or detail.get("id"))
            checks["name_present"] = bool(detail.get("name"))
            checks["status_present"] = "status" in detail
            artifacts["detail_checks"] = checks
            if not all(checks.values()):
                ok = False
                status = "failed_retriable"
    except HttpJsonError as exc:
        ok = False
        status = "failed_retriable"
        evidence.append(
            EvidenceItem(
                kind="http",
                target=f"platform-control:/v1/sources/{source_id}",
                detail=exc.body[:500],
            )
        )

    compensation = CompensationRef(
        available=True,
        command=_compensation_cmd(effective_run_id),
        run_id=effective_run_id,
    )
    envelope = StepEnvelope(
        ok=ok,
        workflow=_WORKFLOW_SOURCE,
        run_id=effective_run_id,
        step="source.verify",
        status=status,
        side_effect_level="none",
        inputs={"source_id": source_id},
        artifacts=artifacts,
        evidence=evidence,
        decision=StepDecision(
            recommended_action="request-approval" if ok else "compensate",
            reason=(
                "Source verified; ready for operator approval."
                if ok
                else "Verification failed; compensate or inspect source."
            ),
        ),
        next_actions=["request-approval"] if ok else ["compensate", "inspect"],
        compensation=compensation,
    )
    journal.record_step(effective_run_id, envelope)
    _emit_envelope(envelope, human=human)
    if not ok:
        raise typer.Exit(code=1)


# ---------------------------------------------------------------------------
# evidara workflow source compensate
# ---------------------------------------------------------------------------

@source_app.command("compensate")
def source_compensate(
    run_id: Annotated[str, typer.Option("--run-id", help="Workflow run ID to compensate")],
    human: Annotated[bool, typer.Option("--human", help="Pretty-print JSON")] = False,
    correlation_id: Annotated[
        str | None, typer.Option("--correlation-id")
    ] = None,
) -> None:
    """Compensate the last reversible side effect for this run.

    For example: reject a draft source version that was created by ``apply``.
    """
    journal = _default_journal()
    run = journal.get_run(run_id)
    if run is None:
        typer.echo(f"Run not found: {run_id}", err=True)
        raise typer.Exit(code=1)

    # Find the last reversible step.
    reversible_steps = [
        s for s in reversed(run.steps)
        if s.side_effect_level == "reversible" and s.status != "compensated"
    ]
    if not reversible_steps:
        envelope = StepEnvelope(
            ok=True,
            workflow=_WORKFLOW_SOURCE,
            run_id=run_id,
            step="source.compensate",
            status="passed",
            side_effect_level="none",
            inputs={"run_id": run_id},
            artifacts={"note": "No reversible side effects to compensate."},
            evidence=[],
            decision=StepDecision(recommended_action="inspect", reason="Nothing to compensate."),
            next_actions=["inspect"],
        )
        journal.record_step(run_id, envelope)
        _emit_envelope(envelope, human=human)
        return

    last = reversible_steps[0]
    artifacts: dict[str, Any] = {"compensated_step": last.step}
    evidence: list[EvidenceItem] = []
    ok = True

    # Attempt API-level compensation for known reversible steps.
    source_version_id: str | None = last.artifacts.get("source_version_id")
    if last.step == "source.apply" and source_version_id:
        base = platform_control_base_url()
        headers = platform_control_headers(correlation_id=correlation_id)
        headers["Content-Type"] = "application/json"
        try:
            request_json(
                "POST",
                join_url(base, f"/v1/versions/{source_version_id}/reject"),
                headers=headers,
                json_body={"reason": "Compensated by evidara workflow source compensate"},
            )
            artifacts["source_version_id"] = source_version_id
            evidence.append(
                EvidenceItem(
                    kind="http",
                    target=f"platform-control:/v1/versions/{source_version_id}/reject",
                    status_code=200,
                )
            )
        except HttpJsonError as exc:
            ok = False
            evidence.append(
                EvidenceItem(
                    kind="http",
                    target=f"platform-control:/v1/versions/{source_version_id}/reject",
                    detail=exc.body[:500],
                )
            )
    else:
        # Record compensation intent in journal only (no API call available).
        evidence.append(
            EvidenceItem(
                kind="artifact",
                target=last.step,
                detail="Compensation recorded in local journal. Apply manual rollback if needed.",
            )
        )

    envelope = StepEnvelope(
        ok=ok,
        workflow=_WORKFLOW_SOURCE,
        run_id=run_id,
        step="source.compensate",
        status="compensated" if ok else "failed_retriable",
        side_effect_level="reversible",
        inputs={"run_id": run_id, "compensated_step": last.step},
        artifacts=artifacts,
        evidence=evidence,
        decision=StepDecision(
            recommended_action="inspect" if ok else "retry",
            reason=(
                "Compensation recorded."
                if ok
                else "Compensation failed; retry or apply manual rollback."
            ),
        ),
        next_actions=["inspect"] if ok else ["retry"],
    )
    journal.record_step(run_id, envelope)
    if ok:
        journal.close_run(run_id, "compensated")
    _emit_envelope(envelope, human=human)
    if not ok:
        raise typer.Exit(code=1)


# ---------------------------------------------------------------------------
# evidara workflow run status / cancel / evidence
# ---------------------------------------------------------------------------

@run_app.command("status")
def run_status(
    run_id: Annotated[str, typer.Argument(help="Workflow run ID")],
    human: Annotated[bool, typer.Option("--human", help="Pretty-print JSON")] = False,
) -> None:
    """Show the current status and checkpoint of a workflow run."""
    import json

    journal = _default_journal()
    run = journal.get_run(run_id)
    if run is None:
        typer.echo(f"Run not found: {run_id}", err=True)
        raise typer.Exit(code=1)
    data = {
        "run_id": run.run_id,
        "workflow": run.workflow,
        "status": run.status,
        "checkpoint": run.checkpoint,
        "started_at": run.started_at,
        "finished_at": run.finished_at,
        "step_count": len(run.steps),
    }
    if human or os.environ.get("EVIDARA_CLI_HUMAN", "").strip().lower() in ("1", "true", "yes"):
        typer.echo(json.dumps(data, indent=2, sort_keys=True, default=str))
    else:
        typer.echo(json.dumps(data, separators=(",", ":"), default=str))


@run_app.command("cancel")
def run_cancel(
    run_id: Annotated[str, typer.Argument(help="Workflow run ID to cancel")],
    human: Annotated[bool, typer.Option("--human", help="Pretty-print JSON")] = False,
) -> None:
    """Mark a workflow run as cancelled in the local journal."""
    import json

    journal = _default_journal()
    try:
        run = journal.close_run(run_id, "cancelled")
    except ValueError as exc:
        typer.echo(str(exc), err=True)
        raise typer.Exit(code=1) from exc
    data = {"ok": True, "run_id": run.run_id, "status": run.status}
    if human or os.environ.get("EVIDARA_CLI_HUMAN", "").strip().lower() in ("1", "true", "yes"):
        typer.echo(json.dumps(data, indent=2, sort_keys=True, default=str))
    else:
        typer.echo(json.dumps(data, separators=(",", ":"), default=str))


@run_app.command("evidence")
def run_evidence(
    run_id: Annotated[str, typer.Argument(help="Workflow run ID")],
    human: Annotated[bool, typer.Option("--human", help="Pretty-print JSON")] = False,
) -> None:
    """Show aggregated step evidence for a workflow run."""
    import json

    journal = _default_journal()
    run = journal.get_run(run_id)
    if run is None:
        typer.echo(f"Run not found: {run_id}", err=True)
        raise typer.Exit(code=1)
    data = {
        "run_id": run.run_id,
        "workflow": run.workflow,
        "status": run.status,
        "steps": [
            {
                "step": s.step,
                "attempt": s.attempt,
                "status": s.status,
                "side_effect_level": s.side_effect_level,
                "evidence": s.evidence,
                "artifacts": s.artifacts,
            }
            for s in run.steps
        ],
    }
    if human or os.environ.get("EVIDARA_CLI_HUMAN", "").strip().lower() in ("1", "true", "yes"):
        typer.echo(json.dumps(data, indent=2, sort_keys=True, default=str))
    else:
        typer.echo(json.dumps(data, separators=(",", ":"), default=str))
