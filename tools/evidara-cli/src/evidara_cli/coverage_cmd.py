"""Coverage-loop workflow commands (ADR-0030 / ADR-0033).

Three commands covering the parts of the loop an operator or agent previously had to
hand-roll with `curl`:

- ``templates``  — inventory blueprint templates by *why* they are inert and *who* can
  unblock them, not just that they are.
- ``preflight``  — answer "will the loop run on this template, and in which mode?"
  **before** anything is created. ``/v1/runs/readiness`` needs a source version to
  exist; this needs nothing.
- ``watch``      — poll a run to terminal (optionally through DI and projection) and, on
  a stall, name the likely cause instead of returning a bare timeout.

Driving the loop itself stays with ``scripts/ch-fedlex-compose-e2e.sh`` — it already
does creation, approval, dispatch, the content gates and the evidence bundle, and
re-implementing it here would be a second copy that drifts. These commands bracket it.

Explicitly **not** ADR-0033 step 6: no protocol server, no retrieval or reasoning tools.
See ``coverage.py``'s module docstring.
"""

from __future__ import annotations

import json
import time
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
from evidara_cli.coverage import (
    MODE_ACCEPTANCE,
    TERMINAL_RUN_STATUSES,
    acceptance_evidence_verdict,
    classify_template,
    diagnose_stall,
    summarise_templates,
)
from evidara_cli.envelope import build_envelope, evidence_assertion, evidence_count, evidence_http

coverage_app = typer.Typer(
    no_args_is_help=True,
    help=(
        "Coverage-loop commands (ADR-0030): inventory blueprint templates by blocker, "
        "pre-flight a template before anything is created, and watch a run with a stall "
        "diagnosis."
    ),
)

_WORKFLOW = "coverage-loop"


def _emit(data: dict[str, Any], *, human: bool) -> None:
    if human:
        typer.echo(json.dumps(data, indent=2, sort_keys=True, default=str))
    else:
        typer.echo(json.dumps(data, separators=(",", ":"), default=str))


def _fail(
    exc: Exception,
    *,
    step: str,
    inputs: dict[str, Any],
    human: bool,
    side_effect_level: str = "none",
) -> None:
    status_code = exc.status_code if isinstance(exc, HttpJsonError) else None
    body = exc.body[:2000] if isinstance(exc, HttpJsonError) else ""
    envelope = build_envelope(
        ok=False,
        workflow=_WORKFLOW,
        step=step,
        status="failed_terminal",
        side_effect_level=side_effect_level,
        inputs=inputs,
        error=str(exc),
        error_detail={"status_code": status_code, "body": body},
        decision={
            "recommended_action": "retry",
            "reason": "Check platform-control reachability and auth env vars.",
        },
        next_actions=["retry", "inspect"],
        compensation={"available": False},
    )
    _emit(envelope, human=human)
    raise typer.Exit(code=1) from exc


def _fetch_templates(*, correlation_id: str | None) -> list[dict[str, Any]]:
    payload = request_json(
        "GET",
        join_url(platform_control_base_url(), "/v1/sources/blueprint-templates"),
        headers=platform_control_headers(correlation_id=correlation_id),
    )
    data = payload.get("data") if isinstance(payload, dict) else payload
    return [item for item in (data or []) if isinstance(item, dict)]


# ---------------------------------------------------------------------------------
# coverage templates
# ---------------------------------------------------------------------------------


@coverage_app.command("templates")
def coverage_templates(
    overlay: Annotated[
        str | None,
        typer.Option("--overlay", help="Filter by overlay id (ch, at, de, eu, fr)."),
    ] = None,
    provider: Annotated[
        str | None,
        typer.Option("--provider", help="Filter by acquisition provider name."),
    ] = None,
    template: Annotated[
        str | None,
        typer.Option("--template", help="Filter by provider_template_id (exact match)."),
    ] = None,
    readiness: Annotated[
        str | None,
        typer.Option(
            "--readiness",
            help="Filter by ADR-0030 code key: scaffold, awaiting_evidence, live.",
        ),
    ] = None,
    blocker: Annotated[
        str | None,
        typer.Option(
            "--blocker",
            help=(
                "Filter by blocker kind: provider_scaffold, provider_awaiting_evidence, "
                "template_disabled_by_operator, template_never_enabled, none."
            ),
        ),
    ] = None,
    mode: Annotated[
        str | None,
        typer.Option("--mode", help="Keep only templates a run of this mode would dispatch."),
    ] = None,
    human: Annotated[bool, typer.Option("--human", help="Pretty-print JSON")] = False,
    correlation_id: Annotated[str | None, typer.Option("--correlation-id")] = None,
) -> None:
    """Inventory blueprint templates with a machine-readable lock verdict per template.

    Each row carries `blocker` and `remedy` codes derived from `acquisition_readiness`
    and the config key's provenance — not from the prose in `notes`. Filter by
    `--blocker provider_awaiting_evidence` to list exactly the templates an operator can
    unblock today without an engineer.
    """
    step = "coverage.templates"
    inputs: dict[str, Any] = {
        "overlay": overlay,
        "provider": provider,
        "template": template,
        "readiness": readiness,
        "blocker": blocker,
        "mode": mode,
    }
    try:
        raw = _fetch_templates(correlation_id=correlation_id)
        classified = [classify_template(item) for item in raw]

        def keep(item: dict[str, Any]) -> bool:
            if overlay and item["overlay_id"] != overlay:
                return False
            if provider and item["provider"] != provider:
                return False
            if template and item["provider_template_id"] != template:
                return False
            if readiness and item["code_key"] != readiness:
                return False
            if blocker and (item["blocker"] or "none") != blocker:
                return False
            return not (mode and mode not in item["dispatchable_modes"])

        rows = [item for item in classified if keep(item)]
        summary = summarise_templates(rows)
        disagreements = [item for item in rows if not item["agrees_with_server"]]

        ev = [
            evidence_http(
                "platform-control:/v1/sources/blueprint-templates",
                status_code=200,
                note=f"{len(raw)} templates in the inventory",
            ),
            evidence_count(
                "coverage:matched-templates",
                value=len(rows),
                passed=True,
                note=f"{len(rows)} templates matched the filters",
            ),
            evidence_assertion(
                "coverage:classification-agrees-with-server",
                value=len(disagreements),
                passed=not disagreements,
                note=(
                    "Client-side lock derivation matches the server's `launchable`."
                    if not disagreements
                    else (
                        "Client-side lock derivation DISAGREES with the server's "
                        "`launchable` for at least one template. Trust "
                        "/v1/runs/readiness, not this output, and file a bug — the "
                        "CLI's mirror of the two-key rule has drifted."
                    )
                ),
            ),
        ]
        ok = not disagreements
        _emit(
            build_envelope(
                ok=ok,
                workflow=_WORKFLOW,
                step=step,
                status="passed" if ok else "needs_human",
                side_effect_level="none",
                inputs=inputs,
                artifacts={"summary": summary, "templates": rows},
                evidence=ev,
                decision={
                    "recommended_action": "preflight" if ok else "needs-human",
                    "reason": (
                        f"{summary['acceptance_ready']} of {summary['total']} templates can "
                        "dispatch an acceptance run today; "
                        f"{summary['needs_engineering']} need engineering."
                    )
                    if ok
                    else "Classification disagrees with the server. Do not act on this output.",
                },
                next_actions=["preflight", "inspect"],
                compensation={"available": False},
            ),
            human=human,
        )
        if not ok:
            raise typer.Exit(code=1)
    except typer.Exit:
        raise
    except Exception as exc:
        _fail(exc, step=step, inputs=inputs, human=human)


# ---------------------------------------------------------------------------------
# coverage preflight
# ---------------------------------------------------------------------------------


@coverage_app.command("preflight")
def coverage_preflight(
    overlay: Annotated[str, typer.Option("--overlay", help="Overlay id, e.g. ch.")],
    template: Annotated[
        str,
        typer.Option("--template", help="provider_template_id to pre-flight."),
    ],
    check_search: Annotated[
        bool,
        typer.Option(
            "--check-search/--no-check-search",
            help="Also check legal-search reachability (the loop ends there).",
        ),
    ] = True,
    human: Annotated[bool, typer.Option("--human", help="Pretty-print JSON")] = False,
    correlation_id: Annotated[str | None, typer.Option("--correlation-id")] = None,
) -> None:
    """Answer "will the loop run on this template, and in which mode?" — creating nothing.

    `/v1/runs/readiness` is authoritative but needs a source *and* a version to already
    exist, so today the only way to learn a template is inert is to create both and be
    refused. This resolves the two-key lock, resolves the acquisition spec via
    `POST /v1/sources/blueprint-preview` (which surfaces provider config errors and the
    seed URLs it would hit), and checks both services — all read-only.
    """
    step = "coverage.preflight"
    inputs: dict[str, Any] = {"overlay": overlay, "template": template}
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
                note="platform-control reachable",
            )
        )

        raw = _fetch_templates(correlation_id=correlation_id)
        match = next(
            (
                item
                for item in raw
                if item.get("overlay_id") == overlay
                and item.get("provider_template_id") == template
            ),
            None,
        )
        if match is None:
            ev.append(
                evidence_assertion(
                    "coverage:template-exists",
                    value=f"{overlay}/{template}",
                    passed=False,
                    note=(
                        "No such blueprint template. Run `evidara workflow coverage "
                        "templates --overlay <id>` to list what exists."
                    ),
                )
            )
            _emit(
                build_envelope(
                    ok=False,
                    workflow=_WORKFLOW,
                    step=step,
                    status="failed_terminal",
                    side_effect_level="none",
                    inputs=inputs,
                    evidence=ev,
                    decision={
                        "recommended_action": "inspect",
                        "reason": f"Template '{overlay}/{template}' does not exist.",
                    },
                    next_actions=["inspect"],
                    compensation={"available": False},
                ),
                human=human,
            )
            raise typer.Exit(code=1)

        verdict = classify_template(match)
        artifacts["template"] = verdict
        ev.append(
            evidence_assertion(
                "coverage:two-key-lock",
                value=verdict["lock_state"],
                passed=bool(verdict["dispatchable_modes"]),
                note=verdict["remedy_detail"] or "Both ADR-0030 keys are turned.",
            )
        )
        if not verdict["agrees_with_server"]:
            ev.append(
                evidence_assertion(
                    "coverage:classification-agrees-with-server",
                    value=False,
                    passed=False,
                    note=(
                        "Client-side lock derivation disagrees with the server's "
                        "`launchable`. Trust /v1/runs/readiness and file a bug."
                    ),
                )
            )

        # Resolve the spec. This is where a provider config error or a missing seed
        # surfaces — before a source, a version and an approval have been spent on it.
        try:
            preview = request_json(
                "POST",
                join_url(pc_base, "/v1/sources/blueprint-preview"),
                headers={**pc_headers, "Content-Type": "application/json"},
                json_body={"overlay_id": overlay, "provider_template_id": template},
            )
            plan_notes = list(preview.get("plan_notes") or []) if isinstance(preview, dict) else []
            artifacts["acquisition_spec"] = (
                preview.get("acquisition_spec") if isinstance(preview, dict) else None
            )
            artifacts["plan_notes"] = plan_notes
            ev.append(
                evidence_http(
                    "platform-control:/v1/sources/blueprint-preview",
                    status_code=200,
                    note=(
                        f"Acquisition spec resolves; provider reported {len(plan_notes)} "
                        "plan note(s). Read them: they describe the acquisition itself "
                        "(seed URLs, config errors), not the lock."
                    ),
                )
            )
        except HttpJsonError as exc:
            ev.append(
                evidence_http(
                    "platform-control:/v1/sources/blueprint-preview",
                    status_code=exc.status_code or 0,
                    passed=False,
                    note=(
                        "The acquisition spec did not resolve. The loop cannot run until "
                        f"this is fixed: {exc.body[:400]}"
                    ),
                )
            )

        if check_search:
            search_code = request_status(
                "GET",
                join_url(legal_search_base_url(), "/health"),
                headers=legal_search_headers(correlation_id=correlation_id),
                timeout=30.0,
            )
            ev.append(
                evidence_http(
                    "legal-search:/health",
                    status_code=search_code,
                    note=(
                        "legal-search reachable — the loop's final assertion is that the "
                        "document becomes searchable."
                    ),
                )
            )

        recommended_mode = verdict["recommended_mode"]
        if recommended_mode:
            artifacts["next_command"] = (
                "bash scripts/ch-fedlex-compose-e2e.sh "
                f"--overlay {overlay} --template {template} --mode {recommended_mode}"
            )
            if recommended_mode == MODE_ACCEPTANCE:
                artifacts["acceptance_note"] = (
                    "mode=acceptance is a rehearsal against the live portal to produce "
                    "evidence. It does NOT imply either ADR-0030 key is turned "
                    "(ADR-0030 §6)."
                )

        ok = all(item.get("passed", True) for item in ev)
        _emit(
            build_envelope(
                ok=ok,
                workflow=_WORKFLOW,
                step=step,
                status="passed" if ok else "needs_human",
                side_effect_level="none",
                inputs=inputs,
                artifacts=artifacts,
                evidence=ev,
                decision={
                    "recommended_action": "run-acceptance-loop" if ok else verdict["remedy"],
                    "reason": (
                        f"Template is dispatchable with mode={recommended_mode}."
                        if ok
                        else verdict["remedy_detail"]
                        or "One or more pre-flight checks did not pass."
                    ),
                },
                next_actions=["watch", "inspect"] if ok else ["inspect"],
                compensation={"available": False},
            ),
            human=human,
        )
        if not ok:
            raise typer.Exit(code=1)
    except typer.Exit:
        raise
    except Exception as exc:
        _fail(exc, step=step, inputs=inputs, human=human)


# ---------------------------------------------------------------------------------
# coverage watch
# ---------------------------------------------------------------------------------


def _sleep(seconds: float) -> None:
    """Indirection so tests can drive the poll loop without waiting."""
    time.sleep(seconds)


def _pipeline_stage_status(health: dict[str, Any], name: str) -> str | None:
    for stage in health.get("stages") or []:
        if isinstance(stage, dict) and stage.get("stage") == name:
            status = stage.get("status")
            return str(status) if status is not None else None
    return None


@coverage_app.command("watch")
def coverage_watch(
    run_id: Annotated[str, typer.Option("--run-id", help="Run id to watch.")],
    until: Annotated[
        str,
        typer.Option(
            "--until",
            help=(
                "'run' waits for a terminal run status; 'processed' also waits for DI "
                "and projection to report."
            ),
        ),
    ] = "run",
    timeout: Annotated[
        float,
        typer.Option(
            "--timeout",
            min=0.0,
            help="Seconds to wait before giving up. 0 polls once and reports.",
        ),
    ] = 600.0,
    interval: Annotated[
        float,
        typer.Option("--interval", min=0.0, help="Seconds between polls."),
    ] = 5.0,
    human: Annotated[bool, typer.Option("--human", help="Pretty-print JSON")] = False,
    correlation_id: Annotated[str | None, typer.Option("--correlation-id")] = None,
) -> None:
    """Poll a run to terminal and diagnose a stall instead of returning a bare timeout.

    A run that never leaves PENDING, or one that completes while document-intelligence
    hears nothing, are both silent in `/v1/runs/{id}` alone. This joins the run with
    `/v1/runs/{id}/pipeline-health` and names the likely cause with a code an agent can
    branch on — including the two that cost the most time driving the loop: no
    dispatch worker, and a publish path left on `noop`.
    """
    if until not in ("run", "processed"):
        typer.echo("--until must be 'run' or 'processed'.", err=True)
        raise typer.Exit(code=2)

    step = "coverage.watch"
    inputs: dict[str, Any] = {
        "run_id": run_id,
        "until": until,
        "timeout": timeout,
        "interval": interval,
    }
    pc_base = platform_control_base_url()
    pc_headers = platform_control_headers(correlation_id=correlation_id)

    try:
        deadline = time.monotonic() + timeout
        run: dict[str, Any] = {}
        health: dict[str, Any] = {}
        polls = 0
        reached = False

        while True:
            polls += 1
            run_payload = request_json(
                "GET", join_url(pc_base, f"/v1/runs/{run_id}"), headers=pc_headers
            )
            run = run_payload if isinstance(run_payload, dict) else {}
            health_payload = request_json(
                "GET",
                join_url(pc_base, f"/v1/runs/{run_id}/pipeline-health"),
                headers=pc_headers,
            )
            health = health_payload if isinstance(health_payload, dict) else {}

            status = str(run.get("status") or "").lower()
            terminal = status in TERMINAL_RUN_STATUSES
            if until == "run":
                reached = terminal
            else:
                di = _pipeline_stage_status(health, "document_intelligence")
                projection = _pipeline_stage_status(health, "projection")
                reached = terminal and di == "ok" and projection == "ok"
                # A blocked or failed stage is terminal too — waiting longer is pointless.
                if terminal and (
                    di in {"blocked", "failed"} or projection in {"blocked", "failed"}
                ):
                    break
            # A refused run is FAILED at creation; stop immediately rather than polling.
            if reached or bool(run.get("refused")):
                break
            if time.monotonic() >= deadline:
                break
            _sleep(interval)

        refused = bool(run.get("refused"))
        ok = reached and not refused

        ev = [
            evidence_assertion(
                "coverage:run-status",
                value=run.get("status"),
                passed=str(run.get("status") or "").lower() == "completed",
                note=f"Run reached status '{run.get('status')}' after {polls} poll(s).",
            ),
            evidence_assertion(
                "coverage:pipeline-overall-status",
                value=health.get("overall_status"),
                passed=health.get("overall_status") not in {"blocked", "failed"},
                note=f"pipeline-health stages: {len(health.get('stages') or [])}",
            ),
        ]

        artifacts: dict[str, Any] = {
            "run": run,
            "pipeline_health": health,
            "polls": polls,
            "reached_target": reached,
        }
        decision: dict[str, Any]
        if ok:
            decision = {
                "recommended_action": "evidence",
                "reason": (
                    "Target state reached. Collect evidence with "
                    f"`evidara workflow run evidence --run-id {run_id}`."
                ),
            }
        else:
            diagnosis = diagnose_stall(run, health)
            artifacts["stall_diagnosis"] = diagnosis
            ev.append(
                evidence_assertion(
                    "coverage:stall-diagnosis",
                    value=diagnosis["cause"],
                    passed=False,
                    note=diagnosis["detail"],
                )
            )
            decision = {
                "recommended_action": "needs-human",
                "reason": diagnosis["detail"],
            }

        _emit(
            build_envelope(
                ok=ok,
                workflow=_WORKFLOW,
                step=step,
                run_id=run_id,
                status="passed" if ok else "needs_human",
                side_effect_level="none",
                inputs=inputs,
                artifacts=artifacts,
                evidence=ev,
                decision=decision,
                next_actions=["evidence"] if ok else ["inspect", "compensate"],
                compensation={
                    "available": not ok and not refused,
                    "command": f"evidara workflow source compensate --run-id {run_id}"
                    if not ok and not refused
                    else None,
                },
            ),
            human=human,
        )
        if not ok:
            raise typer.Exit(code=1)
    except typer.Exit:
        raise
    except Exception as exc:
        _fail(exc, step=step, inputs=inputs, human=human)


__all__ = ["coverage_app", "acceptance_evidence_verdict"]
