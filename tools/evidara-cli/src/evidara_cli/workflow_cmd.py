"""Workflow sub-commands for evidara-cli.

Implements the verb family (inspect, propose, apply, verify, compensate) for
source-lifecycle, search, and run-management workflows as defined by ADR-0022.

Every command returns a WorkflowCommandEnvelope JSON document conforming to
contracts/schemas/workflow-command-envelope.schema.json.
"""

from __future__ import annotations

from typing import Annotated, Any

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
from evidara_cli.coverage import acceptance_evidence_verdict
from evidara_cli.envelope import (
    build_envelope,
    evidence_assertion,
    evidence_count,
    evidence_http,
)
from evidara_cli.proposal import SourceSpecProposal

# ---------------------------------------------------------------------------
# Sub-app definitions
# ---------------------------------------------------------------------------

workflow_source_app = typer.Typer(
    no_args_is_help=True,
    help="Source-lifecycle workflow commands (inspect, propose, apply, verify, compensate).",
)
workflow_search_app = typer.Typer(
    no_args_is_help=True,
    help="Search workflow commands (inspect, verify).",
)
workflow_run_app = typer.Typer(
    no_args_is_help=True,
    help="Workflow run management commands (status, evidence).",
)

# ---------------------------------------------------------------------------
# Shared helpers
# ---------------------------------------------------------------------------

_WORKFLOW_SOURCE = "source-lifecycle"
_WORKFLOW_SEARCH = "search-verification"
_WORKFLOW_RUN = "run-management"


def _emit_envelope(data: dict[str, Any], *, human: bool) -> None:
    import json

    if human:
        typer.echo(json.dumps(data, indent=2, sort_keys=True, default=str))
    else:
        typer.echo(json.dumps(data, separators=(",", ":"), default=str))


def _fail_envelope(
    exc: Exception,
    *,
    workflow: str,
    step: str,
    side_effect_level: str,
    inputs: dict[str, Any],
    human: bool,
) -> None:
    status_code: int | None = None
    body = ""
    if isinstance(exc, HttpJsonError):
        status_code = exc.status_code
        body = exc.body[:2000]
    envelope = build_envelope(
        ok=False,
        workflow=workflow,
        step=step,
        status="failed_terminal",
        side_effect_level=side_effect_level,
        inputs=inputs,
        error=str(exc),
        error_detail={"status_code": status_code, "body": body} if status_code else None,
        decision={"recommended_action": "retry", "reason": "Check service reachability."},
        next_actions=["retry", "inspect"],
        compensation={"available": False},
    )
    _emit_envelope(envelope, human=human)
    raise typer.Exit(code=1) from exc


# ---------------------------------------------------------------------------
# workflow source inspect
# ---------------------------------------------------------------------------


@workflow_source_app.command("inspect")
def source_inspect(
    source_id: Annotated[
        str | None,
        typer.Option("--source-id", help="Optional source id to inspect."),
    ] = None,
    human: Annotated[bool, typer.Option("--human", help="Pretty-print JSON")] = False,
    correlation_id: Annotated[str | None, typer.Option("--correlation-id")] = None,
) -> None:
    """Read-only reachability and source discovery checks against platform-control."""
    step = "source.inspect"
    inputs: dict[str, Any] = {"source_id": source_id}
    pc_base = platform_control_base_url()
    pc_headers = platform_control_headers(correlation_id=correlation_id)

    ev: list[dict[str, Any]] = []
    artifacts: dict[str, Any] = {}

    try:
        health_code = request_status("GET", join_url(pc_base, "/health"), headers=pc_headers)
        ev.append(
            evidence_http(
                "platform-control:/health",
                status_code=health_code,
                note="Platform-control health check",
            )
        )

        if source_id:
            source_payload = request_json(
                "GET",
                join_url(pc_base, f"/v1/sources/{source_id}"),
                headers=pc_headers,
            )
            ev.append(
                evidence_http(
                    f"platform-control:/v1/sources/{source_id}",
                    status_code=200,
                    note="Source detail fetch",
                )
            )
            artifacts["source"] = source_payload
        else:
            sources_payload = request_json(
                "GET",
                join_url(pc_base, "/v1/sources"),
                headers=pc_headers,
            )
            if isinstance(sources_payload, list):
                source_count = len(sources_payload)
            elif isinstance(sources_payload, dict):
                items = sources_payload.get("data", sources_payload.get("items", []))
                source_count = len(items) if isinstance(items, list) else 0
            else:
                source_count = 0
            ev.append(
                evidence_count(
                    "platform-control:/v1/sources",
                    value=source_count,
                    passed=True,
                    note="Existing source count",
                )
            )
            artifacts["source_count"] = source_count

        all_passed = all(e.get("passed", True) for e in ev)
        envelope = build_envelope(
            ok=all_passed and health_code < 400,
            workflow=_WORKFLOW_SOURCE,
            step=step,
            status="passed" if all_passed and health_code < 400 else "failed_retriable",
            side_effect_level="none",
            inputs=inputs,
            artifacts=artifacts,
            evidence=ev,
            decision={
                "recommended_action": "propose",
                "reason": "Platform-control is reachable. Proceed to propose a spec.",
            },
            next_actions=["propose", "verify"],
            compensation={"available": False},
        )
        _emit_envelope(envelope, human=human)
    except Exception as exc:
        _fail_envelope(
            exc,
            workflow=_WORKFLOW_SOURCE,
            step=step,
            side_effect_level="none",
            inputs=inputs,
            human=human,
        )


# ---------------------------------------------------------------------------
# workflow source propose
# ---------------------------------------------------------------------------


@workflow_source_app.command("propose")
def source_propose(
    seed_url: Annotated[
        str,
        typer.Option("--seed-url", help="Seed URL for the new source (required)."),
    ],
    human: Annotated[bool, typer.Option("--human", help="Pretty-print JSON")] = False,
    correlation_id: Annotated[str | None, typer.Option("--correlation-id")] = None,
) -> None:
    """Propose an acquisition spec for a new source (DSPy-optional, read-only)."""
    step = "source.propose"
    inputs: dict[str, Any] = {"seed_url": seed_url}
    pc_base = platform_control_base_url()
    pc_headers = platform_control_headers(correlation_id=correlation_id)

    ev: list[dict[str, Any]] = []

    try:
        sources_payload = request_json(
            "GET",
            join_url(pc_base, "/v1/sources"),
            headers=pc_headers,
        )
        existing_names: list[str] = []
        if isinstance(sources_payload, list):
            existing_names = [
                s.get("display_name", "") for s in sources_payload if isinstance(s, dict)
            ]
        elif isinstance(sources_payload, dict):
            items = sources_payload.get("data", sources_payload.get("items", []))
            existing_names = [s.get("display_name", "") for s in items if isinstance(s, dict)]

        ev.append(
            evidence_count(
                "platform-control:/v1/sources",
                value=len(existing_names),
                passed=True,
                note="Existing source names fetched for duplicate check",
            )
        )

        proposer = SourceSpecProposal()
        proposal_result = proposer.propose(
            seed_url,
            existing_source_names=existing_names,
        )

        duplicate_risk = proposal_result.get("duplicate_risk", "none")
        ev.append(
            evidence_assertion(
                "duplicate-check",
                value=duplicate_risk,
                passed=duplicate_risk != "high",
                note=f"Duplicate risk assessment: {duplicate_risk}",
            )
        )

        all_passed = all(e.get("passed", True) for e in ev)
        status = "passed" if all_passed else "needs_human"
        recommended_action = "apply" if duplicate_risk == "none" else "needs-human"
        reason = (
            "No duplicate detected. Review the proposed spec and run apply to create a draft."
            if duplicate_risk == "none"
            else f"Duplicate risk is '{duplicate_risk}'. Review before applying."
        )

        envelope = build_envelope(
            ok=all_passed,
            workflow=_WORKFLOW_SOURCE,
            step=step,
            status=status,
            side_effect_level="none",
            inputs=inputs,
            artifacts={"proposal": proposal_result},
            evidence=ev,
            decision={"recommended_action": recommended_action, "reason": reason},
            next_actions=["apply", "inspect"] if all_passed else ["inspect"],
            compensation={"available": False},
        )
        _emit_envelope(envelope, human=human)
        if not all_passed:
            raise typer.Exit(code=1)
    except typer.Exit:
        raise
    except Exception as exc:
        _fail_envelope(
            exc,
            workflow=_WORKFLOW_SOURCE,
            step=step,
            side_effect_level="none",
            inputs=inputs,
            human=human,
        )


# ---------------------------------------------------------------------------
# workflow source apply
# ---------------------------------------------------------------------------


@workflow_source_app.command("apply")
def source_apply(
    display_name: Annotated[
        str,
        typer.Option("--display-name", help="Source display name."),
    ],
    seed_url: Annotated[
        str,
        typer.Option("--seed-url", help="Seed URL for the source."),
    ],
    jurisdiction_id: Annotated[
        str | None,
        typer.Option("--jurisdiction-id", help="Jurisdiction id from reference data."),
    ] = None,
    human: Annotated[bool, typer.Option("--human", help="Pretty-print JSON")] = False,
    correlation_id: Annotated[str | None, typer.Option("--correlation-id")] = None,
) -> None:
    """Create a draft source in platform-control (reversible mutating action)."""
    step = "source.apply"
    inputs: dict[str, Any] = {
        "display_name": display_name,
        "seed_url": seed_url,
        "jurisdiction_id": jurisdiction_id,
    }
    pc_base = platform_control_base_url()
    pc_headers = platform_control_headers(correlation_id=correlation_id)
    pc_headers["Content-Type"] = "application/json"

    ev: list[dict[str, Any]] = []

    try:
        body: dict[str, Any] = {
            "display_name": display_name,
            "seed_url": seed_url,
        }
        if jurisdiction_id:
            body["jurisdiction_id"] = jurisdiction_id

        created = request_json(
            "POST",
            join_url(pc_base, "/v1/sources"),
            headers=pc_headers,
            json_body=body,
        )
        source_id = created.get("source_id") if isinstance(created, dict) else None
        ev.append(
            evidence_http(
                "platform-control:/v1/sources",
                status_code=201,
                note="Draft source created",
            )
        )
        ev.append(
            evidence_assertion(
                "source-id-present",
                value=source_id,
                passed=bool(source_id),
                note="Created source id",
            )
        )

        envelope = build_envelope(
            ok=bool(source_id),
            workflow=_WORKFLOW_SOURCE,
            step=step,
            status="passed" if source_id else "failed_retriable",
            side_effect_level="reversible",
            inputs=inputs,
            artifacts={"source_id": source_id, "source": created},
            evidence=ev,
            decision={
                "recommended_action": "verify",
                "reason": (
                    "Draft source created. Run verify to confirm state, or compensate to reject."
                ),
            },
            next_actions=["verify", "compensate"],
            compensation={
                "available": True,
                "command": f"evidara workflow source compensate --source-id {source_id}",
                "note": "Reject or delete the draft source to compensate.",
            },
        )
        _emit_envelope(envelope, human=human)
        if not source_id:
            raise typer.Exit(code=1)
    except typer.Exit:
        raise
    except Exception as exc:
        _fail_envelope(
            exc,
            workflow=_WORKFLOW_SOURCE,
            step=step,
            side_effect_level="reversible",
            inputs=inputs,
            human=human,
        )


# ---------------------------------------------------------------------------
# workflow source verify
# ---------------------------------------------------------------------------


@workflow_source_app.command("verify")
def source_verify(
    source_id: Annotated[
        str | None,
        typer.Option("--source-id", help="Source id to verify."),
    ] = None,
    run_id: Annotated[
        str | None,
        typer.Option("--run-id", help="Run id to verify (alternative to --source-id)."),
    ] = None,
    human: Annotated[bool, typer.Option("--human", help="Pretty-print JSON")] = False,
    correlation_id: Annotated[str | None, typer.Option("--correlation-id")] = None,
) -> None:
    """Verify the current state of a source or run (read-only evidence collection)."""
    if not source_id and not run_id:
        typer.echo("Provide --source-id or --run-id.", err=True)
        raise typer.Exit(code=2)

    step = "source.verify"
    inputs: dict[str, Any] = {"source_id": source_id, "run_id": run_id}
    pc_base = platform_control_base_url()
    pc_headers = platform_control_headers(correlation_id=correlation_id)

    ev: list[dict[str, Any]] = []
    artifacts: dict[str, Any] = {}

    try:
        if source_id:
            payload = request_json(
                "GET",
                join_url(pc_base, f"/v1/sources/{source_id}"),
                headers=pc_headers,
            )
            ev.append(
                evidence_http(
                    f"platform-control:/v1/sources/{source_id}",
                    status_code=200,
                    note="Source detail fetch",
                )
            )
            state = payload.get("status") if isinstance(payload, dict) else None
            ev.append(
                evidence_assertion(
                    "source-status",
                    value=state,
                    passed=state is not None,
                    note=f"Source status: {state}",
                )
            )
            artifacts["source"] = payload

        if run_id:
            run_payload = request_json(
                "GET",
                join_url(pc_base, f"/v1/runs/{run_id}"),
                headers=pc_headers,
            )
            ev.append(
                evidence_http(
                    f"platform-control:/v1/runs/{run_id}",
                    status_code=200,
                    note="Run detail fetch",
                )
            )
            run_status = run_payload.get("status") if isinstance(run_payload, dict) else None
            ev.append(
                evidence_assertion(
                    "run-status",
                    value=run_status,
                    passed=run_status is not None,
                    note=f"Run status: {run_status}",
                )
            )
            artifacts["run"] = run_payload

        all_passed = all(e.get("passed", True) for e in ev)
        envelope = build_envelope(
            ok=all_passed,
            workflow=_WORKFLOW_SOURCE,
            step=step,
            status="passed" if all_passed else "needs_human",
            side_effect_level="none",
            inputs=inputs,
            artifacts=artifacts,
            evidence=ev,
            decision={
                "recommended_action": "approve" if all_passed else "needs-human",
                "reason": "Verification complete. Review evidence before approval."
                if all_passed
                else "One or more checks did not pass. Review before continuing.",
            },
            next_actions=["compensate"] if not all_passed else ["inspect"],
            compensation={"available": True} if not all_passed else {"available": False},
        )
        _emit_envelope(envelope, human=human)
        if not all_passed:
            raise typer.Exit(code=1)
    except typer.Exit:
        raise
    except Exception as exc:
        _fail_envelope(
            exc,
            workflow=_WORKFLOW_SOURCE,
            step=step,
            side_effect_level="none",
            inputs=inputs,
            human=human,
        )


# ---------------------------------------------------------------------------
# workflow source compensate
# ---------------------------------------------------------------------------


@workflow_source_app.command("compensate")
def source_compensate(
    source_id: Annotated[
        str | None,
        typer.Option("--source-id", help="Source id to compensate (reject pending versions)."),
    ] = None,
    run_id: Annotated[
        str | None,
        typer.Option("--run-id", help="Run id to cancel as compensation."),
    ] = None,
    reason: Annotated[
        str,
        typer.Option("--reason", help="Human-readable reason for the compensating action."),
    ] = "Operator-initiated compensation via evidara-cli.",
    human: Annotated[bool, typer.Option("--human", help="Pretty-print JSON")] = False,
    correlation_id: Annotated[str | None, typer.Option("--correlation-id")] = None,
) -> None:
    """Explicitly compensate a reversible source-lifecycle action.

    Compensation is distinct from reasoning backtracking: it executes a real corrective
    action in platform-control rather than silently undoing in memory.
    """
    if not source_id and not run_id:
        typer.echo("Provide --source-id or --run-id.", err=True)
        raise typer.Exit(code=2)

    step = "source.compensate"
    inputs: dict[str, Any] = {"source_id": source_id, "run_id": run_id, "reason": reason}
    pc_base = platform_control_base_url()
    pc_headers = platform_control_headers(correlation_id=correlation_id)
    pc_headers["Content-Type"] = "application/json"

    ev: list[dict[str, Any]] = []
    artifacts: dict[str, Any] = {}

    try:
        if run_id:
            cancel_payload = request_json(
                "POST",
                join_url(pc_base, f"/v1/runs/{run_id}/cancel"),
                headers=pc_headers,
                json_body={"reason": reason},
            )
            ev.append(
                evidence_http(
                    f"platform-control:/v1/runs/{run_id}/cancel",
                    status_code=200,
                    note="Run cancellation request accepted",
                )
            )
            artifacts["cancel_response"] = cancel_payload

        if source_id:
            # Reject the latest pending_approval version if one exists.
            versions_payload = request_json(
                "GET",
                join_url(pc_base, f"/v1/sources/{source_id}/versions"),
                headers=pc_headers,
            )
            versions_list: list[Any] = []
            if isinstance(versions_payload, list):
                versions_list = versions_payload
            elif isinstance(versions_payload, dict):
                versions_list = versions_payload.get("data", versions_payload.get("items", []))
            pending_versions = [
                v
                for v in versions_list
                if isinstance(v, dict) and v.get("status") in ("pending_approval", "draft")
            ]
            if pending_versions:
                version_id = pending_versions[0].get("source_version_id")
                if version_id:
                    reject_payload = request_json(
                        "POST",
                        join_url(pc_base, f"/v1/versions/{version_id}/reject"),
                        headers=pc_headers,
                        json_body={"reason": reason},
                    )
                    ev.append(
                        evidence_http(
                            f"platform-control:/v1/versions/{version_id}/reject",
                            status_code=200,
                            note="Pending source version rejected",
                        )
                    )
                    artifacts["rejected_version_id"] = version_id
                    artifacts["reject_response"] = reject_payload
            else:
                ev.append(
                    evidence_assertion(
                        f"platform-control:/v1/sources/{source_id}/versions",
                        value="no-pending-versions",
                        passed=True,
                        note="No pending versions found; compensation recorded as intent only.",
                    )
                )

        all_passed = all(e.get("passed", True) for e in ev)
        envelope = build_envelope(
            ok=all_passed,
            workflow=_WORKFLOW_SOURCE,
            step=step,
            status="compensated" if all_passed else "failed_terminal",
            side_effect_level="reversible",
            inputs=inputs,
            artifacts=artifacts,
            evidence=ev,
            decision={
                "recommended_action": "inspect",
                "reason": "Compensation applied. Inspect current state before continuing.",
            },
            next_actions=["inspect"],
            compensation={"available": False},
        )
        _emit_envelope(envelope, human=human)
        if not all_passed:
            raise typer.Exit(code=1)
    except typer.Exit:
        raise
    except Exception as exc:
        _fail_envelope(
            exc,
            workflow=_WORKFLOW_SOURCE,
            step=step,
            side_effect_level="reversible",
            inputs=inputs,
            human=human,
        )


# ---------------------------------------------------------------------------
# workflow search inspect
# ---------------------------------------------------------------------------


@workflow_search_app.command("inspect")
def search_inspect(
    human: Annotated[bool, typer.Option("--human", help="Pretty-print JSON")] = False,
    correlation_id: Annotated[str | None, typer.Option("--correlation-id")] = None,
) -> None:
    """Read-only reachability check for legal-search."""
    step = "search.inspect"
    inputs: dict[str, Any] = {}
    ls_base = legal_search_base_url()
    ls_headers = legal_search_headers(correlation_id=correlation_id)

    ev: list[dict[str, Any]] = []

    try:
        code = request_status(
            "GET",
            join_url(ls_base, "/v1/search"),
            headers=ls_headers,
            params={"q": "test", "page": "1", "page_size": "1"},
            timeout=30.0,
        )
        ev.append(
            evidence_http(
                "legal-search:/v1/search",
                status_code=code,
                note="Legal-search reachability check",
            )
        )

        ok = code < 400
        envelope = build_envelope(
            ok=ok,
            workflow=_WORKFLOW_SEARCH,
            step=step,
            status="passed" if ok else "failed_retriable",
            side_effect_level="none",
            inputs=inputs,
            evidence=ev,
            decision={
                "recommended_action": "verify" if ok else "retry",
                "reason": "Legal-search is reachable." if ok else "Legal-search is not reachable.",
            },
            next_actions=["verify"] if ok else ["retry"],
            compensation={"available": False},
        )
        _emit_envelope(envelope, human=human)
        if not ok:
            raise typer.Exit(code=1)
    except typer.Exit:
        raise
    except Exception as exc:
        _fail_envelope(
            exc,
            workflow=_WORKFLOW_SEARCH,
            step=step,
            side_effect_level="none",
            inputs=inputs,
            human=human,
        )


# ---------------------------------------------------------------------------
# workflow search verify
# ---------------------------------------------------------------------------


@workflow_search_app.command("verify")
def search_verify(
    queries: Annotated[
        list[str],
        typer.Option("--query", "-q", help="Search query to verify (repeatable)."),
    ],
    min_results: Annotated[
        int,
        typer.Option("--min-results", help="Minimum total results expected per query."),
    ] = 1,
    human: Annotated[bool, typer.Option("--human", help="Pretty-print JSON")] = False,
    correlation_id: Annotated[str | None, typer.Option("--correlation-id")] = None,
) -> None:
    """Run a query pack against legal-search and verify minimum result counts."""
    step = "search.verify"
    inputs: dict[str, Any] = {"queries": queries, "min_results": min_results}
    ls_base = legal_search_base_url()
    ls_headers = legal_search_headers(correlation_id=correlation_id)

    ev: list[dict[str, Any]] = []
    query_results: list[dict[str, Any]] = []

    try:
        for q in queries:
            payload = request_json(
                "GET",
                join_url(ls_base, "/v1/search"),
                headers=ls_headers,
                params={"q": q, "page": "1", "page_size": "10"},
                timeout=60.0,
            )
            total = (
                payload.get("totalResults", payload.get("total_results", 0))
                if isinstance(payload, dict)
                else 0
            )
            passed = isinstance(total, int) and total >= min_results
            ev.append(
                evidence_count(
                    f"legal-search:/v1/search?q={q}",
                    value=total if isinstance(total, int) else 0,
                    passed=passed,
                    note=f"Query '{q}': {total} results (min {min_results})",
                )
            )
            query_results.append({"query": q, "total_results": total, "passed": passed})

        all_passed = all(e.get("passed", True) for e in ev)
        envelope = build_envelope(
            ok=all_passed,
            workflow=_WORKFLOW_SEARCH,
            step=step,
            status="passed" if all_passed else "failed_retriable",
            side_effect_level="none",
            inputs=inputs,
            artifacts={"query_results": query_results},
            evidence=ev,
            decision={
                "recommended_action": "approve" if all_passed else "needs-human",
                "reason": "All queries meet minimum result threshold."
                if all_passed
                else "One or more queries returned fewer results than expected.",
            },
            next_actions=["inspect"] if all_passed else ["inspect", "compensate"],
            compensation={"available": False},
        )
        _emit_envelope(envelope, human=human)
        if not all_passed:
            raise typer.Exit(code=1)
    except typer.Exit:
        raise
    except Exception as exc:
        _fail_envelope(
            exc,
            workflow=_WORKFLOW_SEARCH,
            step=step,
            side_effect_level="none",
            inputs=inputs,
            human=human,
        )


# ---------------------------------------------------------------------------
# workflow run status
# ---------------------------------------------------------------------------


@workflow_run_app.command("status")
def run_status(
    run_id: Annotated[str, typer.Option("--run-id", help="Workflow run id.")],
    human: Annotated[bool, typer.Option("--human", help="Pretty-print JSON")] = False,
    correlation_id: Annotated[str | None, typer.Option("--correlation-id")] = None,
) -> None:
    """Get the current status of a platform-control run."""
    step = "run.status"
    inputs: dict[str, Any] = {"run_id": run_id}
    pc_base = platform_control_base_url()
    pc_headers = platform_control_headers(correlation_id=correlation_id)

    ev: list[dict[str, Any]] = []

    try:
        payload = request_json(
            "GET",
            join_url(pc_base, f"/v1/runs/{run_id}"),
            headers=pc_headers,
        )
        ev.append(
            evidence_http(
                f"platform-control:/v1/runs/{run_id}",
                status_code=200,
                note="Run detail fetch",
            )
        )
        run_s = payload.get("status") if isinstance(payload, dict) else None
        ev.append(
            evidence_assertion(
                "run-status-present",
                value=run_s,
                passed=run_s is not None,
                note=f"Run status: {run_s}",
            )
        )

        all_passed = all(e.get("passed", True) for e in ev)
        envelope = build_envelope(
            ok=all_passed,
            workflow=_WORKFLOW_RUN,
            step=step,
            status="passed" if all_passed else "failed_retriable",
            side_effect_level="none",
            inputs=inputs,
            artifacts={"run": payload},
            evidence=ev,
            decision={
                "recommended_action": "verify" if run_s == "completed" else "inspect",
                "reason": f"Run status is '{run_s}'.",
            },
            next_actions=["verify", "compensate"],
            compensation={
                "available": run_s not in ("completed", "cancelled"),
                "command": f"evidara workflow source compensate --run-id {run_id}"
                if run_s not in ("completed", "cancelled")
                else None,
            },
        )
        _emit_envelope(envelope, human=human)
    except Exception as exc:
        _fail_envelope(
            exc,
            workflow=_WORKFLOW_RUN,
            step=step,
            side_effect_level="none",
            inputs=inputs,
            human=human,
        )


# ---------------------------------------------------------------------------
# workflow run evidence
# ---------------------------------------------------------------------------


@workflow_run_app.command("evidence")
def run_evidence(
    run_id: Annotated[str, typer.Option("--run-id", help="Workflow run id.")],
    human: Annotated[bool, typer.Option("--human", help="Pretty-print JSON")] = False,
    correlation_id: Annotated[str | None, typer.Option("--correlation-id")] = None,
) -> None:
    """Collect evidence artifacts for a completed platform-control run.

    Also renders the **ADR-0030 acceptance verdict**: whether this run may be cited as
    the acceptance evidence that justifies flipping a template's config key. The verdict
    refuses a SHADOW-mode version outright — it replays cassettes and never reaches the
    live portal, so it proves nothing about it (ADR-0030 §2) — as well as a refused run,
    a non-acceptance mode, and a run that captured nothing.
    """
    step = "run.evidence"
    inputs: dict[str, Any] = {"run_id": run_id}
    pc_base = platform_control_base_url()
    pc_headers = platform_control_headers(correlation_id=correlation_id)

    ev: list[dict[str, Any]] = []
    artifacts: dict[str, Any] = {}

    try:
        run_payload = request_json(
            "GET",
            join_url(pc_base, f"/v1/runs/{run_id}"),
            headers=pc_headers,
        )
        ev.append(
            evidence_http(
                f"platform-control:/v1/runs/{run_id}",
                status_code=200,
                note="Run detail",
            )
        )
        artifacts["run"] = run_payload

        # Collect captured resources as evidence of run output.
        try:
            resources_payload = request_json(
                "GET",
                join_url(pc_base, f"/v1/runs/{run_id}/captured-resources"),
                headers=pc_headers,
            )
            if isinstance(resources_payload, list):
                resource_count = len(resources_payload)
            elif isinstance(resources_payload, dict):
                items = resources_payload.get("data", resources_payload.get("items", []))
                resource_count = len(items) if isinstance(items, list) else 0
            else:
                resource_count = 0
            ev.append(
                evidence_count(
                    f"platform-control:/v1/runs/{run_id}/captured-resources",
                    value=resource_count,
                    passed=True,
                    note=f"Captured resources: {resource_count}",
                )
            )
            artifacts["captured_resource_count"] = resource_count
        except HttpJsonError:
            # Non-fatal: captured-resources endpoint may not be available for all run types.
            ev.append(
                evidence_assertion(
                    f"platform-control:/v1/runs/{run_id}/captured-resources",
                    value="unavailable",
                    passed=True,
                    note="Captured-resources endpoint not available for this run type.",
                )
            )

        # Pipeline health names where the loop actually stopped: acquisition,
        # document_intelligence, projection, search. Non-fatal if unavailable.
        try:
            health_payload = request_json(
                "GET",
                join_url(pc_base, f"/v1/runs/{run_id}/pipeline-health"),
                headers=pc_headers,
            )
            if isinstance(health_payload, dict):
                artifacts["pipeline_health"] = health_payload
                ev.append(
                    evidence_assertion(
                        f"platform-control:/v1/runs/{run_id}/pipeline-health",
                        value=health_payload.get("overall_status"),
                        passed=health_payload.get("overall_status") not in ("blocked", "failed"),
                        note=f"Pipeline overall status: {health_payload.get('overall_status')}",
                    )
                )
        except HttpJsonError:
            ev.append(
                evidence_assertion(
                    f"platform-control:/v1/runs/{run_id}/pipeline-health",
                    value="unavailable",
                    passed=True,
                    note="Pipeline-health endpoint not available for this run.",
                )
            )

        # ADR-0030 acceptance verdict. `execution_mode` lives on the source version, and
        # there is no GET /v1/versions/{id}, so resolve it through the source's list.
        execution_mode: str | None = None
        source_id = run_payload.get("source_id") if isinstance(run_payload, dict) else None
        version_id = run_payload.get("source_version_id") if isinstance(run_payload, dict) else None
        if source_id and version_id:
            try:
                versions_payload = request_json(
                    "GET",
                    join_url(pc_base, f"/v1/sources/{source_id}/versions"),
                    headers=pc_headers,
                )
                versions = (
                    versions_payload.get("data", [])
                    if isinstance(versions_payload, dict)
                    else versions_payload or []
                )
                for version in versions:
                    if isinstance(version, dict) and version.get("source_version_id") == version_id:
                        execution_mode = version.get("execution_mode")
                        break
            except HttpJsonError:
                execution_mode = None

        verdict = acceptance_evidence_verdict(
            run=run_payload if isinstance(run_payload, dict) else {},
            execution_mode=execution_mode,
            captured_resources_count=artifacts.get("captured_resource_count"),
        )
        artifacts["acceptance_verdict"] = verdict
        ev.append(
            evidence_assertion(
                "adr-0030:acceptance-evidence",
                value=verdict["is_acceptance_evidence"],
                # Not a failure of the command: most runs are legitimately not
                # acceptance evidence. Reported, never silently implied.
                passed=True,
                note=(
                    "This run may be cited as ADR-0030 acceptance evidence."
                    if verdict["is_acceptance_evidence"]
                    else "REFUSED as acceptance evidence: "
                    + "; ".join(r["code"] for r in verdict["refusals"])
                ),
            )
        )

        all_passed = all(e.get("passed", True) for e in ev)
        envelope = build_envelope(
            ok=all_passed,
            workflow=_WORKFLOW_RUN,
            step=step,
            status="passed" if all_passed else "failed_retriable",
            side_effect_level="none",
            inputs=inputs,
            artifacts=artifacts,
            evidence=ev,
            decision={
                "recommended_action": "flip-enablement"
                if verdict["is_acceptance_evidence"]
                else "verify",
                "reason": (
                    "Acceptance evidence captured. Read the harness's skipped-gate list "
                    "before flipping `enabled: true` (ADR-0030 §5)."
                    if verdict["is_acceptance_evidence"]
                    else "Evidence collected, but this run is not ADR-0030 acceptance "
                    "evidence. Review `acceptance_verdict.refusals`."
                ),
            },
            next_actions=["verify", "inspect"],
            compensation={"available": False},
        )
        _emit_envelope(envelope, human=human)
    except Exception as exc:
        _fail_envelope(
            exc,
            workflow=_WORKFLOW_RUN,
            step=step,
            side_effect_level="none",
            inputs=inputs,
            human=human,
        )
