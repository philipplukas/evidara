"""Workflow verb commands for the evidara CLI.

Implements the five-verb control surface from ADR-0022:
  inspect   — read-only reachability and state discovery
  propose   — produce a draft plan or spec without mutating state
  apply     — execute a reversible mutating action
  verify    — collect post-action evidence and evaluate
  compensate — explicitly recover from a reversible side effect

Commands are grouped into three sub-typers:
  source  — source lifecycle workflows
  search  — search-serving verification workflows
  run     — workflow run management

Each command returns a consistent JSON envelope (see workflow_envelope.py).
"""

from __future__ import annotations

import uuid
from datetime import UTC, datetime
from typing import Annotated, Any

import httpx
import typer

from evidara_cli.client import (
    HttpJsonError,
    join_url,
    legal_search_base_url,
    legal_search_headers,
    platform_control_base_url,
    platform_control_headers,
    request_json,
    request_status,
)
from evidara_cli.journal import LocalJournal, WorkflowStepRun
from evidara_cli.proposal import propose_source_spec
from evidara_cli.workflow_envelope import (
    SideEffectLevel,
    StepStatus,
    build_envelope,
    compensation_command,
    evidence_check,
    evidence_http,
)

# ---------------------------------------------------------------------------
# Sub-typers
# ---------------------------------------------------------------------------

source_app = typer.Typer(
    no_args_is_help=True,
    help="Source lifecycle workflow commands (inspect/propose/apply/verify/compensate).",
)
search_app = typer.Typer(
    no_args_is_help=True,
    help="Search-serving verification workflow commands.",
)
run_app = typer.Typer(
    no_args_is_help=True,
    help="Workflow run management commands.",
)

# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------

_HUMAN_OPTION = typer.Option("--human", help="Pretty-print JSON (also EVIDARA_CLI_HUMAN=1)")
_CORRELATION_OPTION = typer.Option("--correlation-id", help="Forwarded as X-Correlation-Id")
_RUN_ID_OPTION = typer.Option("--run-id", help="Workflow run identifier from a previous step")


def _new_run_id(prefix: str) -> str:
    ts = datetime.now(UTC).strftime("%Y%m%d_%H%M%S")
    short = uuid.uuid4().hex[:6]
    return f"wf_{prefix}_{ts}_{short}"


def _emit(data: Any, *, human: bool) -> None:
    import json
    import os

    human_out = human or os.environ.get("EVIDARA_CLI_HUMAN", "").strip().lower() in (
        "1",
        "true",
        "yes",
    )
    if human_out:
        typer.echo(json.dumps(data, indent=2, sort_keys=True, default=str))
    else:
        typer.echo(json.dumps(data, separators=(",", ":"), default=str))


def _record_step(
    journal: LocalJournal,
    *,
    run_id: str,
    step: str,
    side_effect_level: SideEffectLevel,
    status: StepStatus,
    inputs: dict[str, Any],
    artifacts: dict[str, Any],
    evidence: list[dict[str, Any]],
    correlation_id: str | None,
) -> None:
    journal.record_step(
        WorkflowStepRun(
            run_id=run_id,
            step=step,
            attempt=1,
            side_effect_level=side_effect_level,
            status=status,
            inputs=inputs,
            artifacts=artifacts,
            evidence=evidence,
            correlation_id=correlation_id,
        )
    )


# ---------------------------------------------------------------------------
# source inspect
# ---------------------------------------------------------------------------


@source_app.command("inspect")
def source_inspect(
    source_id: Annotated[
        str | None,
        typer.Option("--source-id", help="Optional existing source ID to look up"),
    ] = None,
    run_id: Annotated[str | None, _RUN_ID_OPTION] = None,
    human: Annotated[bool, _HUMAN_OPTION] = False,
    correlation_id: Annotated[str | None, _CORRELATION_OPTION] = None,
) -> None:
    """Inspect environment reachability and optional source state (read-only)."""
    wf_run_id = run_id or _new_run_id("source")
    journal = LocalJournal()
    journal.create_run(wf_run_id, "source-draft", inputs={"source_id": source_id})

    pc_base = platform_control_base_url()
    pc_headers = platform_control_headers(correlation_id=correlation_id)

    evidence: list[dict[str, Any]] = []
    artifacts: dict[str, Any] = {}

    try:
        with httpx.Client(timeout=30.0, follow_redirects=True) as client:
            health_code = request_status(
                "GET", join_url(pc_base, "/health"), headers=pc_headers, client=client
            )
            evidence.append(
                evidence_http("platform-control:/health", status_code=health_code)
            )

            sources_code = request_status(
                "GET", join_url(pc_base, "/v1/sources"), headers=pc_headers, client=client
            )
            evidence.append(
                evidence_http("platform-control:/v1/sources", status_code=sources_code)
            )

            if source_id:
                source_url = join_url(pc_base, f"/v1/sources/{source_id}")
                try:
                    source_data = request_json(
                        "GET", source_url, headers=pc_headers, client=client
                    )
                    artifacts["source"] = source_data
                    evidence.append(
                        evidence_http(
                            f"platform-control:/v1/sources/{source_id}", status_code=200
                        )
                    )
                except HttpJsonError as exc:
                    evidence.append(
                        evidence_http(
                            f"platform-control:/v1/sources/{source_id}",
                            status_code=exc.status_code or 0,
                            ok=False,
                        )
                    )

        pc_ok = health_code == 200
        # 401/403 on /v1/sources means the service is reachable but credentials are not
        # configured for this environment — a separate configuration concern from reachability.
        sources_ok = sources_code in (200, 401, 403)
        all_ok = pc_ok and sources_ok

        status: StepStatus = "passed" if all_ok else "failed_retriable"
        next_actions = (
            ["propose", "inspect"]
            if all_ok
            else ["retry", "check-environment"]
        )

        _record_step(
            journal,
            run_id=wf_run_id,
            step="source.inspect",
            side_effect_level="none",
            status=status,
            inputs={"source_id": source_id},
            artifacts=artifacts,
            evidence=evidence,
            correlation_id=correlation_id,
        )
        journal.complete_run(wf_run_id, status=status, checkpoint="source.inspect")

        envelope = build_envelope(
            ok=all_ok,
            workflow="source-draft",
            run_id=wf_run_id,
            step="source.inspect",
            status=status,
            side_effect_level="none",
            inputs={"source_id": source_id},
            artifacts=artifacts,
            evidence=evidence,
            decision={
                "recommended_action": "propose" if all_ok else "check-environment",
                "reason": (
                    "Platform-control is reachable; safe to proceed to propose step."
                    if all_ok
                    else "Platform-control health check failed; verify service availability."
                ),
            },
            next_actions=next_actions,
        )
        _emit(envelope, human=human)
        if not all_ok:
            raise typer.Exit(code=1)
    except HttpJsonError as exc:
        envelope = build_envelope(
            ok=False,
            workflow="source-draft",
            run_id=wf_run_id,
            step="source.inspect",
            status="failed_retriable",
            side_effect_level="none",
            inputs={"source_id": source_id},
            evidence=evidence,
            decision={"recommended_action": "retry", "reason": str(exc)},
            next_actions=["retry", "check-environment"],
        )
        _emit(envelope, human=human)
        raise typer.Exit(code=1) from exc


# ---------------------------------------------------------------------------
# source propose
# ---------------------------------------------------------------------------


@source_app.command("propose")
def source_propose(
    seed_url: Annotated[str, typer.Option("--seed-url", help="Seed URL for the source")],
    name: Annotated[
        str | None,
        typer.Option("--name", help="Optional name hint (derived from domain if omitted)"),
    ] = None,
    run_id: Annotated[str | None, _RUN_ID_OPTION] = None,
    human: Annotated[bool, _HUMAN_OPTION] = False,
    correlation_id: Annotated[str | None, _CORRELATION_OPTION] = None,
) -> None:
    """Propose a source acquisition spec from a seed URL (read-only, no mutations)."""
    wf_run_id = run_id or _new_run_id("source")
    journal = LocalJournal()
    journal.create_run(wf_run_id, "source-draft", inputs={"seed_url": seed_url, "name": name})

    spec = propose_source_spec(seed_url, name)
    evidence = [
        evidence_check(
            "proposal_has_name",
            passed=bool(spec.get("name")),
            detail=str(spec.get("name", "")),
        ),
        evidence_check(
            "proposal_has_strategy",
            passed=bool(spec.get("acquisition_strategy")),
        ),
        evidence_check(
            "proposal_requires_review",
            passed=bool(spec.get("requires_review")),
        ),
    ]
    all_passed = all(e["passed"] for e in evidence)

    _record_step(
        journal,
        run_id=wf_run_id,
        step="source.propose",
        side_effect_level="none",
        status="passed" if all_passed else "failed_terminal",
        inputs={"seed_url": seed_url, "name": name},
        artifacts={"spec": spec},
        evidence=evidence,
        correlation_id=correlation_id,
    )
    journal.complete_run(
        wf_run_id,
        status="passed" if all_passed else "failed",
        checkpoint="source.propose",
    )

    envelope = build_envelope(
        ok=all_passed,
        workflow="source-draft",
        run_id=wf_run_id,
        step="source.propose",
        status="passed" if all_passed else "failed_terminal",
        side_effect_level="none",
        inputs={"seed_url": seed_url, "name": name},
        artifacts={"spec": spec},
        evidence=evidence,
        decision={
            "recommended_action": "apply" if all_passed else "revise-inputs",
            "reason": (
                f"Proposed spec for {spec.get('name')!r}; review before applying."
                if all_passed
                else "Proposal is incomplete; revise inputs before continuing."
            ),
        },
        next_actions=(
            ["apply", "revise-spec", "inspect"]
            if all_passed
            else ["revise-inputs"]
        ),
    )
    _emit(envelope, human=human)
    if not all_passed:
        raise typer.Exit(code=1)


# ---------------------------------------------------------------------------
# source apply
# ---------------------------------------------------------------------------


@source_app.command("apply")
def source_apply(
    name: Annotated[str, typer.Option("--name", help="Source name (required)")],
    description: Annotated[
        str | None,
        typer.Option("--description", help="Optional source description"),
    ] = None,
    run_id: Annotated[str | None, _RUN_ID_OPTION] = None,
    human: Annotated[bool, _HUMAN_OPTION] = False,
    correlation_id: Annotated[str | None, _CORRELATION_OPTION] = None,
) -> None:
    """Create a draft source via platform-control (reversible mutating action).

    Returns a run ID to use with subsequent verify and compensate commands.
    """
    wf_run_id = run_id or _new_run_id("source")
    journal = LocalJournal()
    journal.create_run(
        wf_run_id,
        "source-draft",
        inputs={"name": name, "description": description},
    )

    pc_base = platform_control_base_url()
    pc_headers = platform_control_headers(correlation_id=correlation_id)
    pc_headers["Content-Type"] = "application/json"
    create_url = join_url(pc_base, "/v1/wizard/projects")

    evidence: list[dict[str, Any]] = []
    body: dict[str, Any] = {"name": name}
    if description:
        body["description"] = description

    try:
        created = request_json("POST", create_url, headers=pc_headers, json_body=body)
        project_id = created.get("wizard_project_id") if isinstance(created, dict) else None
        evidence.append(
            evidence_http(
                "platform-control:/v1/wizard/projects", status_code=200, method="POST"
            )
        )
        evidence.append(
            evidence_check(
                "response_has_project_id",
                passed=bool(project_id),
                detail=str(project_id or ""),
            )
        )

        ok = bool(project_id)
        status: StepStatus = "passed" if ok else "failed_terminal"
        artifacts = {"wizard_project_id": project_id, "created": created}

        _record_step(
            journal,
            run_id=wf_run_id,
            step="source.apply",
            side_effect_level="reversible",
            status=status,
            inputs={"name": name, "description": description},
            artifacts=artifacts,
            evidence=evidence,
            correlation_id=correlation_id,
        )
        journal.complete_run(wf_run_id, status=status, checkpoint="source.apply")

        envelope = build_envelope(
            ok=ok,
            workflow="source-draft",
            run_id=wf_run_id,
            step="source.apply",
            status=status,
            side_effect_level="reversible",
            inputs={"name": name, "description": description},
            artifacts=artifacts,
            evidence=evidence,
            decision={
                "recommended_action": "verify" if ok else "inspect",
                "reason": (
                    f"Draft source created with ID {project_id!r}; proceed to verify."
                    if ok
                    else "Creation response did not include a project ID; inspect and retry."
                ),
            },
            next_actions=["verify", "compensate"] if ok else ["inspect", "retry"],
            compensation=compensation_command(wf_run_id, "source") if ok else {"available": False},
        )
        _emit(envelope, human=human)
        if not ok:
            raise typer.Exit(code=1)
    except HttpJsonError as exc:
        evidence.append(
            evidence_http(
                "platform-control:/v1/wizard/projects",
                status_code=exc.status_code or 0,
                method="POST",
                ok=False,
            )
        )
        _record_step(
            journal,
            run_id=wf_run_id,
            step="source.apply",
            side_effect_level="reversible",
            status="failed_retriable",
            inputs={"name": name, "description": description},
            artifacts={},
            evidence=evidence,
            correlation_id=correlation_id,
        )
        journal.complete_run(wf_run_id, status="failed")
        envelope = build_envelope(
            ok=False,
            workflow="source-draft",
            run_id=wf_run_id,
            step="source.apply",
            status="failed_retriable",
            side_effect_level="reversible",
            inputs={"name": name, "description": description},
            evidence=evidence,
            decision={"recommended_action": "retry", "reason": str(exc)},
            next_actions=["retry", "inspect"],
        )
        _emit(envelope, human=human)
        raise typer.Exit(code=1) from exc


# ---------------------------------------------------------------------------
# source verify
# ---------------------------------------------------------------------------


@source_app.command("verify")
def source_verify(
    project_id: Annotated[
        str,
        typer.Option("--project-id", help="Wizard project ID to verify"),
    ],
    run_id: Annotated[str | None, _RUN_ID_OPTION] = None,
    human: Annotated[bool, _HUMAN_OPTION] = False,
    correlation_id: Annotated[str | None, _CORRELATION_OPTION] = None,
) -> None:
    """Verify that a created source draft is in the expected state."""
    wf_run_id = run_id or _new_run_id("source")
    journal = LocalJournal()
    journal.create_run(wf_run_id, "source-draft", inputs={"project_id": project_id})

    pc_base = platform_control_base_url()
    pc_headers = platform_control_headers(correlation_id=correlation_id)
    get_url = join_url(pc_base, f"/v1/wizard/projects/{project_id}")

    evidence: list[dict[str, Any]] = []
    artifacts: dict[str, Any] = {}

    try:
        fetched = request_json("GET", get_url, headers=pc_headers)
        evidence.append(
            evidence_http(
                f"platform-control:/v1/wizard/projects/{project_id}", status_code=200
            )
        )

        has_id = isinstance(fetched, dict) and "wizard_project_id" in fetched
        has_name = isinstance(fetched, dict) and bool(fetched.get("name"))
        evidence.append(evidence_check("response_has_project_id", passed=has_id))
        evidence.append(evidence_check("response_has_name", passed=has_name))

        artifacts["project"] = fetched
        all_ok = has_id and has_name
        status: StepStatus = "passed" if all_ok else "failed_terminal"

        _record_step(
            journal,
            run_id=wf_run_id,
            step="source.verify",
            side_effect_level="none",
            status=status,
            inputs={"project_id": project_id},
            artifacts=artifacts,
            evidence=evidence,
            correlation_id=correlation_id,
        )
        journal.complete_run(wf_run_id, status=status, checkpoint="source.verify")

        envelope = build_envelope(
            ok=all_ok,
            workflow="source-draft",
            run_id=wf_run_id,
            step="source.verify",
            status=status,
            side_effect_level="none",
            inputs={"project_id": project_id},
            artifacts=artifacts,
            evidence=evidence,
            decision={
                "recommended_action": "approve" if all_ok else "compensate",
                "reason": (
                    "Source draft verified; ready for operator approval."
                    if all_ok
                    else "Source draft state is incomplete; consider compensate or re-apply."
                ),
            },
            next_actions=(
                ["request-approval", "compensate"] if all_ok else ["compensate", "inspect"]
            ),
            compensation=compensation_command(wf_run_id, "source"),
        )
        _emit(envelope, human=human)
        if not all_ok:
            raise typer.Exit(code=1)
    except HttpJsonError as exc:
        evidence.append(
            evidence_http(
                f"platform-control:/v1/wizard/projects/{project_id}",
                status_code=exc.status_code or 0,
                ok=False,
            )
        )
        _record_step(
            journal,
            run_id=wf_run_id,
            step="source.verify",
            side_effect_level="none",
            status="failed_retriable",
            inputs={"project_id": project_id},
            artifacts={},
            evidence=evidence,
            correlation_id=correlation_id,
        )
        journal.complete_run(wf_run_id, status="failed")
        envelope = build_envelope(
            ok=False,
            workflow="source-draft",
            run_id=wf_run_id,
            step="source.verify",
            status="failed_retriable",
            side_effect_level="none",
            inputs={"project_id": project_id},
            evidence=evidence,
            decision={"recommended_action": "retry", "reason": str(exc)},
            next_actions=["retry", "compensate"],
            compensation=compensation_command(wf_run_id, "source"),
        )
        _emit(envelope, human=human)
        raise typer.Exit(code=1) from exc


# ---------------------------------------------------------------------------
# source compensate
# ---------------------------------------------------------------------------


@source_app.command("compensate")
def source_compensate(
    project_id: Annotated[
        str | None,
        typer.Option("--project-id", help="Wizard project ID to mark compensated"),
    ] = None,
    run_id: Annotated[str | None, _RUN_ID_OPTION] = None,
    reason: Annotated[
        str,
        typer.Option("--reason", help="Reason for compensation"),
    ] = "operator-requested",
    human: Annotated[bool, _HUMAN_OPTION] = False,
    correlation_id: Annotated[str | None, _CORRELATION_OPTION] = None,
) -> None:
    """Record a compensation action for a reversible source step.

    Compensation is an explicit recovery event, not an undo.  The journal
    records the intent so operators and agents have a clear audit trail.
    Platform-control durable compensation endpoints will be wired here in
    Phase 2 (see ADR-0022).
    """
    wf_run_id = run_id or _new_run_id("source")
    journal = LocalJournal()
    journal.create_run(
        wf_run_id,
        "source-draft",
        inputs={"project_id": project_id, "reason": reason},
    )

    evidence: list[dict[str, Any]] = [
        evidence_check(
            "compensation_intent_recorded",
            passed=True,
            detail=f"reason={reason!r}",
        ),
        evidence_check(
            "project_id_provided",
            passed=bool(project_id),
            detail=str(project_id or "not provided"),
        ),
    ]

    _record_step(
        journal,
        run_id=wf_run_id,
        step="source.compensate",
        side_effect_level="reversible",
        status="compensated",
        inputs={"project_id": project_id, "reason": reason},
        artifacts={"compensation_run_id": wf_run_id},
        evidence=evidence,
        correlation_id=correlation_id,
    )
    journal.complete_run(wf_run_id, status="compensated", checkpoint="source.compensate")

    envelope = build_envelope(
        ok=True,
        workflow="source-draft",
        run_id=wf_run_id,
        step="source.compensate",
        status="compensated",
        side_effect_level="reversible",
        inputs={"project_id": project_id, "reason": reason},
        artifacts={"compensation_run_id": wf_run_id},
        evidence=evidence,
        decision={
            "recommended_action": "inspect",
            "reason": (
                "Compensation recorded.  Review platform-control to confirm any "
                "required manual cleanup, then re-inspect before retrying."
            ),
        },
        next_actions=["inspect", "propose"],
        compensation={"available": False},
    )
    _emit(envelope, human=human)


# ---------------------------------------------------------------------------
# search inspect
# ---------------------------------------------------------------------------


@search_app.command("inspect")
def search_inspect(
    run_id: Annotated[str | None, _RUN_ID_OPTION] = None,
    human: Annotated[bool, _HUMAN_OPTION] = False,
    correlation_id: Annotated[str | None, _CORRELATION_OPTION] = None,
) -> None:
    """Inspect legal-search reachability (read-only)."""
    wf_run_id = run_id or _new_run_id("search")
    journal = LocalJournal()
    journal.create_run(wf_run_id, "search-verify")

    ls_base = legal_search_base_url()
    ls_headers = legal_search_headers(correlation_id=correlation_id)
    evidence: list[dict[str, Any]] = []

    try:
        with httpx.Client(timeout=30.0, follow_redirects=True) as client:
            search_code = request_status(
                "GET",
                join_url(ls_base, "/v1/search"),
                headers=ls_headers,
                params={"q": "test", "page": "1", "page_size": "1"},
                client=client,
            )
            evidence.append(evidence_http("legal-search:/v1/search", status_code=search_code))

        ok = search_code == 200
        status: StepStatus = "passed" if ok else "failed_retriable"

        _record_step(
            journal,
            run_id=wf_run_id,
            step="search.inspect",
            side_effect_level="none",
            status=status,
            inputs={},
            artifacts={},
            evidence=evidence,
            correlation_id=correlation_id,
        )
        journal.complete_run(wf_run_id, status=status, checkpoint="search.inspect")

        envelope = build_envelope(
            ok=ok,
            workflow="search-verify",
            run_id=wf_run_id,
            step="search.inspect",
            status=status,
            side_effect_level="none",
            evidence=evidence,
            decision={
                "recommended_action": "verify-query-pack" if ok else "check-environment",
                "reason": (
                    "Legal-search is reachable." if ok else "Legal-search returned non-200."
                ),
            },
            next_actions=["verify-query-pack", "verify-document-detail"] if ok else ["retry"],
        )
        _emit(envelope, human=human)
        if not ok:
            raise typer.Exit(code=1)
    except HttpJsonError as exc:
        evidence.append(
            evidence_http(
                "legal-search:/v1/search", status_code=exc.status_code or 0, ok=False
            )
        )
        envelope = build_envelope(
            ok=False,
            workflow="search-verify",
            run_id=wf_run_id,
            step="search.inspect",
            status="failed_retriable",
            side_effect_level="none",
            evidence=evidence,
            decision={"recommended_action": "retry", "reason": str(exc)},
            next_actions=["retry"],
        )
        _emit(envelope, human=human)
        raise typer.Exit(code=1) from exc


# ---------------------------------------------------------------------------
# search verify-query-pack
# ---------------------------------------------------------------------------

_DEFAULT_QUERY_PACK = "art 754,haftung,obligationenrecht"


@search_app.command("verify-query-pack")
def search_verify_query_pack(
    queries: Annotated[
        str,
        typer.Option(
            "--queries",
            help="Comma-separated query strings",
        ),
    ] = _DEFAULT_QUERY_PACK,
    min_results: Annotated[
        int,
        typer.Option("--min-results", min=0, help="Minimum expected total results per query"),
    ] = 1,
    run_id: Annotated[str | None, _RUN_ID_OPTION] = None,
    human: Annotated[bool, _HUMAN_OPTION] = False,
    correlation_id: Annotated[str | None, _CORRELATION_OPTION] = None,
) -> None:
    """Run a query pack against legal-search and evaluate result counts."""
    wf_run_id = run_id or _new_run_id("search")
    journal = LocalJournal()
    journal.create_run(
        wf_run_id,
        "search-verify",
        inputs={"queries": queries, "min_results": min_results},
    )

    ls_base = legal_search_base_url()
    ls_headers = legal_search_headers(correlation_id=correlation_id)

    query_list = [q.strip() for q in queries.split(",") if q.strip()]
    evidence: list[dict[str, Any]] = []
    query_results: list[dict[str, Any]] = []

    try:
        with httpx.Client(timeout=60.0, follow_redirects=True) as client:
            for q in query_list:
                payload = request_json(
                    "GET",
                    join_url(ls_base, "/v1/search"),
                    headers=ls_headers,
                    params={"q": q, "page": "1", "page_size": "10"},
                    client=client,
                )
                total = (
                    # legal-search OpenAPI uses camelCase; tolerate snake_case for resilience
                    # across dev/staging environments and future contract iterations.
                    payload.get("totalResults", payload.get("total_results", 0))
                    if isinstance(payload, dict)
                    else 0
                )
                meets_min = isinstance(total, int) and total >= min_results
                evidence.append(evidence_http("legal-search:/v1/search", status_code=200))
                evidence.append(
                    evidence_check(
                        f"query_results_{q[:20]}",
                        passed=meets_min,
                        detail=f"total={total} min={min_results}",
                    )
                )
                query_results.append({"query": q, "total_results": total, "meets_min": meets_min})

        all_ok = all(r["meets_min"] for r in query_results)
        status: StepStatus = "passed" if all_ok else "failed_retriable"

        _record_step(
            journal,
            run_id=wf_run_id,
            step="search.verify-query-pack",
            side_effect_level="none",
            status=status,
            inputs={"queries": query_list, "min_results": min_results},
            artifacts={"query_results": query_results},
            evidence=evidence,
            correlation_id=correlation_id,
        )
        journal.complete_run(wf_run_id, status=status, checkpoint="search.verify-query-pack")

        envelope = build_envelope(
            ok=all_ok,
            workflow="search-verify",
            run_id=wf_run_id,
            step="search.verify-query-pack",
            status=status,
            side_effect_level="none",
            inputs={"queries": query_list, "min_results": min_results},
            artifacts={"query_results": query_results},
            evidence=evidence,
            decision={
                "recommended_action": "verify-document-detail" if all_ok else "replan",
                "reason": (
                    f"All {len(query_list)} queries returned >= {min_results} results."
                    if all_ok
                    else f"Some queries returned fewer than {min_results} results."
                ),
            },
            next_actions=(
                ["verify-document-detail"] if all_ok else ["replan", "inspect"]
            ),
        )
        _emit(envelope, human=human)
        if not all_ok:
            raise typer.Exit(code=1)
    except HttpJsonError as exc:
        evidence.append(
            evidence_http(
                "legal-search:/v1/search", status_code=exc.status_code or 0, ok=False
            )
        )
        envelope = build_envelope(
            ok=False,
            workflow="search-verify",
            run_id=wf_run_id,
            step="search.verify-query-pack",
            status="failed_retriable",
            side_effect_level="none",
            evidence=evidence,
            decision={"recommended_action": "retry", "reason": str(exc)},
            next_actions=["retry", "inspect"],
        )
        _emit(envelope, human=human)
        raise typer.Exit(code=1) from exc


# ---------------------------------------------------------------------------
# search verify-document-detail
# ---------------------------------------------------------------------------


@search_app.command("verify-document-detail")
def search_verify_document_detail(
    document_id: Annotated[
        str,
        typer.Option("--document-id", help="Document ID to verify"),
    ],
    run_id: Annotated[str | None, _RUN_ID_OPTION] = None,
    human: Annotated[bool, _HUMAN_OPTION] = False,
    correlation_id: Annotated[str | None, _CORRELATION_OPTION] = None,
) -> None:
    """Verify that a document detail endpoint returns a contract-shaped response."""
    wf_run_id = run_id or _new_run_id("search")
    journal = LocalJournal()
    journal.create_run(wf_run_id, "search-verify", inputs={"document_id": document_id})

    ls_base = legal_search_base_url()
    ls_headers = legal_search_headers(correlation_id=correlation_id)
    detail_url = join_url(ls_base, f"/v1/documents/{document_id}")

    evidence: list[dict[str, Any]] = []

    try:
        payload = request_json("GET", detail_url, headers=ls_headers)
        evidence.append(evidence_http(f"legal-search:/v1/documents/{document_id}", status_code=200))

        checks = {
            "id_matches": isinstance(payload, dict) and payload.get("id") == document_id,
            "title_present": isinstance(payload, dict)
            and isinstance(payload.get("title"), str)
            and len(payload.get("title", "").strip()) > 0,
            "subtitle_present": isinstance(payload, dict)
            and isinstance(payload.get("subtitle"), str)
            and len(payload.get("subtitle", "").strip()) > 0,
            "metadata_is_array": isinstance(payload, dict)
            and isinstance(payload.get("metadata"), list),
            "tabs_is_array": isinstance(payload, dict) and isinstance(payload.get("tabs"), list),
        }
        for check_name, passed in checks.items():
            evidence.append(evidence_check(check_name, passed=passed))

        all_ok = all(checks.values())
        status: StepStatus = "passed" if all_ok else "failed_terminal"
        artifacts: dict[str, Any] = {"checks": checks}

        _record_step(
            journal,
            run_id=wf_run_id,
            step="search.verify-document-detail",
            side_effect_level="none",
            status=status,
            inputs={"document_id": document_id},
            artifacts=artifacts,
            evidence=evidence,
            correlation_id=correlation_id,
        )
        journal.complete_run(wf_run_id, status=status, checkpoint="search.verify-document-detail")

        envelope = build_envelope(
            ok=all_ok,
            workflow="search-verify",
            run_id=wf_run_id,
            step="search.verify-document-detail",
            status=status,
            side_effect_level="none",
            inputs={"document_id": document_id},
            artifacts=artifacts,
            evidence=evidence,
            decision={
                "recommended_action": "close" if all_ok else "replan",
                "reason": (
                    "Document detail response is contract-shaped."
                    if all_ok
                    else f"Checks failed: {[k for k, v in checks.items() if not v]!r}"
                ),
            },
            next_actions=["close"] if all_ok else ["replan", "inspect"],
        )
        _emit(envelope, human=human)
        if not all_ok:
            raise typer.Exit(code=1)
    except HttpJsonError as exc:
        evidence.append(
            evidence_http(
                f"legal-search:/v1/documents/{document_id}",
                status_code=exc.status_code or 0,
                ok=False,
            )
        )
        envelope = build_envelope(
            ok=False,
            workflow="search-verify",
            run_id=wf_run_id,
            step="search.verify-document-detail",
            status="failed_retriable",
            side_effect_level="none",
            evidence=evidence,
            decision={"recommended_action": "retry", "reason": str(exc)},
            next_actions=["retry", "inspect"],
        )
        _emit(envelope, human=human)
        raise typer.Exit(code=1) from exc


# ---------------------------------------------------------------------------
# run evidence
# ---------------------------------------------------------------------------


@run_app.command("evidence")
def run_evidence(
    run_id: Annotated[str, typer.Option("--run-id", help="Workflow run ID to summarise")],
    human: Annotated[bool, _HUMAN_OPTION] = False,
) -> None:
    """Show the evidence summary format for a workflow run.

    In Phase 1 (synchronous CLI), workflow state is captured per-command.
    Pass the ``run_id`` from a previous step envelope to document intent;
    the summary reflects the current in-process journal state.
    Phase 2 will query platform-control for durable run history.
    """
    journal = LocalJournal()
    summary = journal.to_evidence_summary(run_id)
    summary["note"] = (
        "Phase 1: in-process journal only. "
        "Durable run history will be available via platform-control in Phase 2 (ADR-0022)."
    )
    _emit(summary, human=human)


@run_app.command("status")
def run_status(
    run_id: Annotated[str, typer.Option("--run-id", help="Workflow run ID to query")],
    human: Annotated[bool, _HUMAN_OPTION] = False,
) -> None:
    """Query status for a workflow run.

    In Phase 1 (synchronous CLI), each command is a separate process; durable
    run state lives in platform-control (not yet implemented).  This command
    returns the run_id back with a status note so agents can record it.
    """
    _emit(
        {
            "run_id": run_id,
            "status": "unknown",
            "note": (
                "Phase 1: durable workflow journal not yet available. "
                "Check platform-control for run state once journal endpoints are added (ADR-0022)."
            ),
        },
        human=human,
    )
