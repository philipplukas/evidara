"""Coverage-loop workflow commands (ADR-0030 / ADR-0033).

Commands covering the parts of the loop an operator or agent previously had to
hand-roll with `curl`:

- ``templates``  — inventory blueprint templates by *why* they are inert and *who* can
  unblock them, not just that they are.
- ``preflight``  — answer "will the loop run on this template, and in which mode?"
  **before** anything is created. ``/v1/runs/readiness`` needs a source version to
  exist; this needs nothing.
- ``watch``      — poll a run to terminal (optionally through DI and projection) and, on
  a stall, name the likely cause instead of returning a bare timeout.
- ``enable``     — the loop's last step: flip the ADR-0030 config key against a cited
  acceptance run, refuse when the run does not earn it, and **read the key back** to
  prove the flip landed.

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
    FLIP_CLASSIFICATION_DISAGREES,
    FLIP_CLASSIFICATION_DISAGREES_DETAIL,
    MODE_ACCEPTANCE,
    TERMINAL_RUN_STATUSES,
    acceptance_evidence_verdict,
    classify_template,
    diagnose_stall,
    is_already_in_desired_state,
    server_refusals,
    summarise_templates,
)
from evidara_cli.envelope import build_envelope, evidence_assertion, evidence_count, evidence_http
from evidara_cli.gate_coverage import load_evidence_bundle

coverage_app = typer.Typer(
    no_args_is_help=True,
    help=(
        "Coverage-loop commands (ADR-0030): inventory blueprint templates by blocker, "
        "pre-flight a template before anything is created, watch a run with a stall "
        "diagnosis, and flip the config key against cited acceptance evidence."
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


# ---------------------------------------------------------------------------------
# coverage enable
# ---------------------------------------------------------------------------------


def _find_template(
    raw: list[dict[str, Any]], *, overlay: str, template: str
) -> dict[str, Any] | None:
    return next(
        (
            item
            for item in raw
            if item.get("overlay_id") == overlay and item.get("provider_template_id") == template
        ),
        None,
    )


def _refusal_envelope(
    *,
    step: str,
    inputs: dict[str, Any],
    artifacts: dict[str, Any],
    refusals: list[dict[str, str]],
    write_attempted: bool = False,
) -> dict[str, Any]:
    """One envelope shape for every refusal, wherever it was derived.

    `write_attempted` is the honest distinction the side-effect level turns on: a
    pre-write refusal changed nothing, while a refusal raised *after* the override row
    was written leaves the key in whatever state the read-back reports.
    """
    return build_envelope(
        ok=False,
        workflow=_WORKFLOW,
        step=step,
        status="needs_human",
        side_effect_level="reversible" if write_attempted else "none",
        inputs=inputs,
        artifacts=artifacts,
        evidence=[
            evidence_assertion(
                "adr-0030:flip-justified",
                value=[item["code"] for item in refusals],
                passed=False,
                note="; ".join(item["detail"] for item in refusals),
            )
        ],
        decision={
            "recommended_action": "needs-human",
            "reason": (
                (
                    "Refused to flip the config key. The write was attempted and the "
                    "read-back did not confirm it. "
                    if write_attempted
                    else "Refused to flip the config key. Nothing was written. "
                )
                + refusals[0]["detail"]
            ),
        },
        next_actions=["inspect"],
        compensation={"available": False},
    )


def _evidence_run(run_id: str, *, correlation_id: str | None) -> dict[str, Any]:
    """Fetch the cited run for the envelope's artifacts.

    Read-only and best-effort: the *verdict* over this run is derived by the server
    (#854), so a failure here costs the envelope some context, never a check.
    """
    try:
        payload = request_json(
            "GET",
            join_url(platform_control_base_url(), f"/v1/runs/{run_id}"),
            headers=platform_control_headers(correlation_id=correlation_id),
        )
    except HttpJsonError:
        return {}
    return payload if isinstance(payload, dict) else {}


@coverage_app.command("enable")
def coverage_enable(
    overlay: Annotated[str, typer.Option("--overlay", help="Overlay id, e.g. ch.")],
    template: Annotated[
        str,
        typer.Option("--template", help="provider_template_id whose config key to flip."),
    ],
    evidence_run_id: Annotated[
        str | None,
        typer.Option(
            "--evidence-run-id",
            help="Run id that earns the flip. Required to enable; ignored when disabling.",
        ),
    ] = None,
    evidence_bundle: Annotated[
        str | None,
        typer.Option(
            "--evidence-bundle",
            help=(
                "Path to the acceptance harness `summary.json` for the cited run. Its "
                "gate ledger decides whether an absent gate was excluded (still "
                "evidence) or not evaluated (refuses the flip)."
            ),
        ),
    ] = None,
    note: Annotated[
        str | None,
        typer.Option("--note", help="Audit note stored with the flip. Required to disable."),
    ] = None,
    enabled: Annotated[
        bool,
        typer.Option("--enable/--disable", help="Turn the config key on (default) or off."),
    ] = True,
    reopen_operator_kill_switch: Annotated[
        bool,
        typer.Option(
            "--reopen-operator-kill-switch",
            help="Acknowledge that you are reopening a key an operator deliberately shut.",
        ),
    ] = False,
    acknowledge_provider_below_live: Annotated[
        bool,
        typer.Option(
            "--acknowledge-provider-below-live",
            help=(
                "Acknowledge arming the config key before the provider's code key "
                "reaches `live` (ADR-0030 §2 requires LIVE)."
            ),
        ),
    ] = False,
    human: Annotated[bool, typer.Option("--human", help="Pretty-print JSON")] = False,
    correlation_id: Annotated[str | None, typer.Option("--correlation-id")] = None,
) -> None:
    """Flip the ADR-0030 config key — against cited evidence, and verified afterwards.

    This is the loop's last step and the one worth getting wrong quietly. Enabling
    requires an `--evidence-run-id` whose run survives the ADR-0030 acceptance verdict
    *and* binds to this template; it refuses outright otherwise, including for a key an
    operator deliberately shut and for a provider whose code key is still below `live`.

    **The guard lives in platform-control, not here (#854).** This command used to
    derive the refusals itself, and the admin panel — hitting the same endpoint —
    required only a non-empty note, so the easier path was the weaker one and this
    command's guard was advisory. The `PUT` now carries the evidence run and both
    acknowledgements, and the server refuses with 409 and the same named codes, which
    are reproduced verbatim in the envelope. It also does the read-back, so a 200 here
    already means the key was re-read and confirmed (#631, #713); this command still
    re-reads the template afterwards to report the resulting lock state.

    The desired state is a *pair*, value and provenance: `--disable` on a key that is
    merely `never_turned` still writes, because ADR-0030's acceptance waiver dispatches
    at a never-turned key and does not at an operator's kill switch (#768).
    """
    if not enabled and not (note or "").strip():
        typer.echo("--note is required when disabling: record why the key was shut.", err=True)
        raise typer.Exit(code=2)

    # An unreadable bundle must stop the command, never degrade to "no gates skipped":
    # a silent fallback here would restore exactly the green-over-nothing read this
    # flag exists to close.
    bundle: dict[str, Any] | None = None
    if evidence_bundle:
        try:
            bundle = load_evidence_bundle(evidence_bundle)
        except (OSError, ValueError) as exc:
            typer.echo(f"--evidence-bundle could not be read: {exc}", err=True)
            raise typer.Exit(code=2) from exc

    step = "coverage.enable"
    inputs: dict[str, Any] = {
        "overlay": overlay,
        "template": template,
        "enabled": enabled,
        "evidence_run_id": evidence_run_id,
        "evidence_bundle": evidence_bundle,
        "reopen_operator_kill_switch": reopen_operator_kill_switch,
        "acknowledge_provider_below_live": acknowledge_provider_below_live,
    }
    pc_base = platform_control_base_url()
    pc_headers = platform_control_headers(correlation_id=correlation_id)

    try:
        raw = _fetch_templates(correlation_id=correlation_id)
        match = _find_template(raw, overlay=overlay, template=template)
        if match is None:
            _emit(
                build_envelope(
                    ok=False,
                    workflow=_WORKFLOW,
                    step=step,
                    status="failed_terminal",
                    side_effect_level="none",
                    inputs=inputs,
                    evidence=[
                        evidence_assertion(
                            "coverage:template-exists",
                            value=f"{overlay}/{template}",
                            passed=False,
                            note=(
                                "No such blueprint template. Nothing was written. List what "
                                "exists with `evidara workflow coverage templates`."
                            ),
                        )
                    ],
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

        before = classify_template(match)
        artifacts: dict[str, Any] = {"template_before": before}

        # Already in the desired state — value *and* provenance. A `--disable` on a key
        # that is merely `never_turned` is NOT a no-op: it must write the override, or
        # the operator believes they installed a kill switch they did not (#768).
        if is_already_in_desired_state(template=match, desired_enabled=enabled):
            _emit(
                build_envelope(
                    ok=True,
                    workflow=_WORKFLOW,
                    step=step,
                    status="passed",
                    side_effect_level="none",
                    inputs=inputs,
                    artifacts={**artifacts, "already_in_desired_state": True},
                    evidence=[
                        evidence_assertion(
                            "coverage:config-key",
                            value=bool(match.get("enabled")),
                            passed=True,
                            note=(
                                f"The config key is already {enabled} and recorded as an "
                                f"operator override ('{before['config_key']}'). Nothing "
                                "was written."
                            ),
                        )
                    ],
                    decision={
                        "recommended_action": "inspect",
                        "reason": "No flip was needed; no request was sent.",
                    },
                    next_actions=["inspect"],
                    compensation={"available": False},
                ),
                human=human,
            )
            return

        # The only refusal still derived here, and it is checked before anything else
        # is read: it compares *this* module's lock derivation against the server's
        # `launchable`, which the server cannot check against itself — and `enable` is
        # the one coverage command whose client-side derivation gates a write, so a
        # disagreement is disqualifying.
        if before.get("agrees_with_server") is False:
            local_refusals = [
                {
                    "code": FLIP_CLASSIFICATION_DISAGREES,
                    "detail": FLIP_CLASSIFICATION_DISAGREES_DETAIL,
                }
            ]
            artifacts["refusals"] = local_refusals
            _emit(
                _refusal_envelope(
                    step=step,
                    inputs=inputs,
                    artifacts=artifacts,
                    refusals=local_refusals,
                ),
                human=human,
            )
            raise typer.Exit(code=1)

        if enabled and evidence_run_id:
            artifacts["evidence_run"] = _evidence_run(
                evidence_run_id, correlation_id=correlation_id
            )

        audit_note = (note or "").strip()
        if enabled and evidence_run_id:
            citation = f"ADR-0030 acceptance evidence: run {evidence_run_id}."
            audit_note = f"{citation} {audit_note}".strip()

        # Everything else is the server's call (#854). A 409 is a refusal that wrote
        # nothing; its `refusals[].code` is the same vocabulary this command used to
        # derive locally, so the envelope reproduces it verbatim.
        try:
            put_response = request_json(
                "PUT",
                join_url(
                    pc_base,
                    f"/v1/sources/blueprint-templates/{overlay}/{template}/enablement",
                ),
                headers={**pc_headers, "Content-Type": "application/json"},
                json_body={
                    "enabled": enabled,
                    "note": audit_note,
                    "evidence_run_id": evidence_run_id if enabled else None,
                    "reopen_operator_kill_switch": reopen_operator_kill_switch,
                    "acknowledge_provider_below_live": acknowledge_provider_below_live,
                },
            )
        except typer.Exit:
            raise
        except HttpJsonError as exc:
            if exc.status_code != 409:
                # The write may or may not have landed, so the envelope must not claim
                # "none" for its side-effect level.
                _fail(exc, step=step, inputs=inputs, human=human, side_effect_level="reversible")
            try:
                body = json.loads(exc.body)
            except (ValueError, TypeError):
                body = None
            refusals = server_refusals(body)
            artifacts["refusals"] = refusals
            artifacts["refusal_response"] = body
            wrote = bool(isinstance(body, dict) and body.get("write_attempted"))
            _emit(
                _refusal_envelope(
                    step=step,
                    inputs=inputs,
                    artifacts=artifacts,
                    refusals=refusals,
                    write_attempted=wrote,
                ),
                human=human,
            )
            raise typer.Exit(code=1) from exc
        except Exception as exc:
            _fail(exc, step=step, inputs=inputs, human=human, side_effect_level="reversible")
        artifacts["enablement_response"] = put_response

        response = put_response if isinstance(put_response, dict) else {}
        artifacts["acceptance_verdict"] = response.get("acceptance_verdict")
        artifacts["evidence_binding"] = response.get("evidence_binding")

        # A 200 already means the server re-read the write and confirmed it. Re-read
        # the inventory anyway: it is what reports the resulting lock state, and an
        # `applied: true` that this cannot corroborate is worth refusing over.
        after_raw = _fetch_templates(correlation_id=correlation_id)
        after_match = _find_template(after_raw, overlay=overlay, template=template) or {}
        after = classify_template(after_match) if after_match else None
        artifacts["template_after"] = after
        server_applied = bool(response.get("applied", True))
        client_agrees = bool(after_match) and (
            bool(after_match.get("enabled")) is bool(enabled)
            and str(after_match.get("source") or "default").lower() == "override"
        )
        artifacts["verification"] = {
            "applied": server_applied and client_agrees,
            "server_applied": server_applied,
            "effective_enabled": after_match.get("enabled"),
            "provenance": after_match.get("source"),
        }

        ev: list[dict[str, Any]] = [
            evidence_http(
                f"platform-control:PUT /v1/sources/blueprint-templates/{overlay}/{template}"
                "/enablement",
                status_code=200,
                note=f"Config key requested: enabled={enabled}.",
            ),
            evidence_assertion(
                "coverage:config-key-read-back",
                value=after_match.get("enabled"),
                passed=server_applied and client_agrees,
                note=(
                    "The server re-read the write and this command re-read the template "
                    f"listing: the key is {after_match.get('enabled')} with provenance "
                    f"'{after_match.get('source')}'."
                ),
            ),
        ]
        binding = response.get("evidence_binding")
        if enabled and binding is not None:
            # `template` is exact — the cited run's version records this overlay and
            # provider template. Anything weaker is reported as a check that did not
            # pass so a human confirms it, rather than a quiet field (#846).
            ev.append(
                evidence_assertion(
                    "adr-0030:acceptance-evidence",
                    value=evidence_run_id,
                    passed=binding == "template",
                    note=(f"Run {evidence_run_id} binds to this template at '{binding}' strength."),
                )
            )
        for reason in response.get("needs_human_reasons") or []:
            ev.append(
                evidence_assertion(
                    "adr-0030:operator-judgement",
                    value=str(reason),
                    passed=False,
                    note=str(reason),
                )
            )

        ok = server_applied and client_agrees
        needs_human = ok and (
            bool(response.get("needs_human")) or any(item.get("passed") is False for item in ev)
        )
        compensate_cmd = (
            "evidara workflow coverage enable --disable "
            f"--overlay {overlay} --template {template} --note '<why>'"
        )
        if not ok:
            status, reason = (
                "failed_terminal",
                "The PUT was accepted but the read-back does not confirm it. "
                "Do not report this key as flipped.",
            )
        elif needs_human:
            status, reason = (
                "needs_human",
                f"Config key for '{overlay}/{template}' is now enabled={enabled}, confirmed "
                "by re-reading the template — but at least one check did not pass. Read the "
                "evidence items marked `passed: false` before treating this as done.",
            )
        else:
            status, reason = (
                "passed",
                f"Config key for '{overlay}/{template}' is now enabled={enabled}, confirmed "
                "by re-reading the template.",
            )
        _emit(
            build_envelope(
                ok=ok,
                workflow=_WORKFLOW,
                step=step,
                status=status,
                side_effect_level="reversible",
                inputs=inputs,
                artifacts=artifacts,
                evidence=ev,
                decision={
                    "recommended_action": "inspect" if ok and not needs_human else "needs-human",
                    "reason": reason,
                },
                next_actions=["inspect", "preflight"],
                compensation={
                    "available": ok,
                    "command": compensate_cmd if ok else None,
                    "note": "Flip the config key back." if ok else None,
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
