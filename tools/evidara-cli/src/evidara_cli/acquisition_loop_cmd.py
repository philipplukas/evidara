"""`evidara workflow coverage drive` — the HTTP half of the acquisition loop (#980).

The decisions live in :mod:`evidara_cli.acquisition_loop`, which has no HTTP and no
clock. This module is the adapter: it turns that protocol into the four platform-control
endpoints the loop is allowed to touch, and wraps the journal in the ADR-0022 envelope
every other workflow command returns.

There is no second control plane here (ADR-0056 constraint 1): every call below is the
same public endpoint an operator would `curl`, with the same auth, and no new server-side
capability was added for the loop. That is the point — a loop that needed its own endpoint
would be a second way to dispatch runs, with its own rules to keep in sync.
"""

from __future__ import annotations

import json
import time
from typing import Annotated, Any

import typer

from evidara_cli.acquisition_loop import (
    STOP_EVIDENCE_CAPTURED,
    STOP_REFUSED,
    BudgetError,
    LoopBudget,
    agent_attribution,
    drive_acquisition,
    readiness_refusals,
)
from evidara_cli.client import (
    HttpJsonError,
    join_url,
    platform_control_base_url,
    platform_control_headers,
    request_json,
)
from evidara_cli.coverage import MODE_ACCEPTANCE
from evidara_cli.envelope import build_envelope, evidence_assertion, evidence_count

_WORKFLOW = "coverage-loop"
_STEP = "coverage.drive"


class HttpLoopClient:
    """The loop's four endpoints, and nothing that writes a spec or a key.

    Every request carries the agent correlation id (ADR-0038): there is no per-person
    identity to record today, so the correlation id is the attribution channel that
    exists, and `agent:` in it is unambiguous in platform-control's logs.
    """

    def __init__(self, *, correlation_id: str) -> None:
        self._base = platform_control_base_url()
        self._headers = platform_control_headers(correlation_id=correlation_id)

    def readiness(self, *, source_id: str, source_version_id: str, mode: str) -> dict[str, Any]:
        payload = request_json(
            "GET",
            join_url(self._base, "/v1/runs/readiness"),
            headers=self._headers,
            params={
                "source_id": source_id,
                "source_version_id": source_version_id,
                "mode": mode,
            },
        )
        return payload if isinstance(payload, dict) else {}

    def launch(
        self, *, source_id: str, source_version_id: str, mode: str, correlation_id: str
    ) -> dict[str, Any]:
        try:
            payload = request_json(
                "POST",
                join_url(self._base, "/v1/runs"),
                headers=platform_control_headers(correlation_id=correlation_id),
                json_body={
                    "source_id": source_id,
                    "source_version_id": source_version_id,
                    "mode": mode,
                },
            )
        except HttpJsonError as exc:
            # A refused dispatch can arrive as a 409 rather than as a persisted refusal
            # record. Reading it as a transport error would let the loop retry it, which
            # is the one thing it must never do — so it is translated into the same
            # refusal shape the loop already treats as terminal.
            if exc.status_code == 409:
                return {
                    "refused": True,
                    "refusal_code": _refusal_code_from_body(exc.body),
                    "failure_reason": exc.body[:1000],
                    "status": "failed",
                }
            raise
        return payload if isinstance(payload, dict) else {}

    def poll(self, run_id: str) -> tuple[dict[str, Any], dict[str, Any]]:
        run = request_json("GET", join_url(self._base, f"/v1/runs/{run_id}"), headers=self._headers)
        health = request_json(
            "GET",
            join_url(self._base, f"/v1/runs/{run_id}/pipeline-health"),
            headers=self._headers,
        )
        return (
            run if isinstance(run, dict) else {},
            health if isinstance(health, dict) else {},
        )

    def cancel(self, run_id: str) -> dict[str, Any]:
        payload = request_json(
            "POST", join_url(self._base, f"/v1/runs/{run_id}/cancel"), headers=self._headers
        )
        return payload if isinstance(payload, dict) else {}

    def sleep(self, seconds: float) -> None:
        time.sleep(seconds)


def _refusal_code_from_body(body: str) -> str:
    """Read a refusal code off an error body, failing closed on an unreadable one.

    Never returns an empty code: an unparseable 409 is still a refusal, and reporting it
    as uncoded is honest where reporting it as absent would read as "not refused".
    """
    try:
        payload = json.loads(body)
    except (ValueError, TypeError):
        return "refused_without_code"
    if isinstance(payload, dict):
        for key in ("refusal_code", "code"):
            value = payload.get(key)
            if isinstance(value, str) and value:
                return value
        refusals = payload.get("refusals")
        if isinstance(refusals, list):
            for item in refusals:
                if isinstance(item, dict) and item.get("code"):
                    return str(item["code"])
    return "refused_without_code"


def _emit(data: dict[str, Any], *, human: bool) -> None:
    if human:
        typer.echo(json.dumps(data, indent=2, sort_keys=True, default=str))
    else:
        typer.echo(json.dumps(data, separators=(",", ":"), default=str))


def coverage_drive(
    source_id: Annotated[str, typer.Option("--source-id", help="Source to acquire.")],
    source_version_id: Annotated[
        str, typer.Option("--source-version-id", help="Approved source version to run.")
    ],
    requests_per_attempt: Annotated[
        int,
        typer.Option(
            "--requests-per-attempt",
            min=1,
            help=(
                "Declared worst-case UPSTREAM requests for ONE attempt of this source — "
                "read it off the spec (limit / max_pages / seed count). Required: "
                "platform-control does not report actual request counts, so an "
                "undeclared cost would make the ceiling meaningless."
            ),
        ),
    ],
    max_attempts: Annotated[
        int, typer.Option("--max-attempts", min=1, help="Launches before the loop stops.")
    ] = 3,
    max_upstream_requests: Annotated[
        int,
        typer.Option(
            "--max-upstream-requests",
            min=1,
            help="Ceiling on authorised upstream requests across the WHOLE loop.",
        ),
    ] = 1000,
    backoff: Annotated[
        float, typer.Option("--backoff", min=0.0, help="Seconds before the 2nd attempt.")
    ] = 30.0,
    backoff_factor: Annotated[
        float, typer.Option("--backoff-factor", min=0.0, help="Exponential growth factor.")
    ] = 2.0,
    max_backoff: Annotated[
        float, typer.Option("--max-backoff", min=0.0, help="Backoff cap in seconds.")
    ] = 300.0,
    poll_interval: Annotated[
        float, typer.Option("--poll-interval", min=0.0, help="Seconds between run polls.")
    ] = 5.0,
    max_polls: Annotated[
        int,
        typer.Option(
            "--max-polls",
            min=1,
            help="Polls per attempt before the run is cancelled rather than watched forever.",
        ),
    ] = 120,
    preflight_only: Annotated[
        bool,
        typer.Option(
            "--preflight-only",
            help=(
                "Report the budget and the readiness verdict and launch nothing. The safe "
                "way to see what the loop would do against a live source."
            ),
        ),
    ] = False,
    agent_id: Annotated[
        str | None,
        typer.Option("--agent-id", help="Agent identity recorded in the journal (ADR-0038)."),
    ] = None,
    human: Annotated[bool, typer.Option("--human", help="Pretty-print JSON")] = False,
) -> None:
    """Drive one source to acceptance evidence, a refusal, or an exhausted budget.

    The loop pre-flights, launches an **acceptance** run, watches it, diagnoses a stall
    with the #950/#985 diagnosis, and either stops with evidence or stops and says why.
    It never flips `enabled: true` (a human's key, #854), never rewrites the spec, and
    never retries a refusal — see :mod:`evidara_cli.acquisition_loop` for why each of
    those is a property of the loop rather than of the server.
    """
    inputs: dict[str, Any] = {
        "source_id": source_id,
        "source_version_id": source_version_id,
        "mode": MODE_ACCEPTANCE,
        "max_attempts": max_attempts,
        "max_upstream_requests": max_upstream_requests,
        "declared_requests_per_attempt": requests_per_attempt,
        "preflight_only": preflight_only,
    }
    try:
        budget = LoopBudget(
            declared_requests_per_attempt=requests_per_attempt,
            max_attempts=max_attempts,
            max_upstream_requests=max_upstream_requests,
            backoff_seconds=backoff,
            backoff_factor=backoff_factor,
            max_backoff_seconds=max_backoff,
            poll_interval_seconds=poll_interval,
            max_polls_per_attempt=max_polls,
        )
    except BudgetError as exc:
        typer.echo(str(exc), err=True)
        raise typer.Exit(code=2) from exc

    attribution = agent_attribution(agent_id=agent_id or "evidara-cli/acquisition-loop")
    client = HttpLoopClient(correlation_id=attribution["correlation_id"])

    try:
        if preflight_only:
            readiness = client.readiness(
                source_id=source_id,
                source_version_id=source_version_id,
                mode=MODE_ACCEPTANCE,
            )
            refusals = readiness_refusals(readiness)
            journal = {
                "ok": not refusals,
                "stop_reason": STOP_REFUSED if refusals else "preflight_only",
                "stop_detail": (
                    "Pre-flight only: nothing was launched and no upstream request was made."
                ),
                "actor": attribution["actor"],
                "agent_id": attribution["agent_id"],
                "correlation_id": attribution["correlation_id"],
                "budget": budget.as_dict(),
                "spend": {
                    "attempts_made": 0,
                    "attempts_remaining": budget.max_attempts,
                    "upstream_requests_authorised": 0,
                    "upstream_requests_remaining": budget.max_upstream_requests,
                    "reconciled_overruns": [],
                },
                "attempts": [],
                "refusals": refusals,
                "readiness": readiness,
                "diagnosis": None,
                "acceptance_evidence": None,
            }
        else:
            journal = drive_acquisition(
                client=client,
                source_id=source_id,
                source_version_id=source_version_id,
                budget=budget,
                agent_id=attribution["agent_id"],
                correlation_id=attribution["correlation_id"],
            )
    except Exception as exc:  # transport/auth — the envelope owns the reporting
        status_code = exc.status_code if isinstance(exc, HttpJsonError) else None
        body = exc.body[:2000] if isinstance(exc, HttpJsonError) else ""
        _emit(
            build_envelope(
                ok=False,
                workflow=_WORKFLOW,
                step=_STEP,
                status="failed_terminal",
                side_effect_level="reversible",
                inputs=inputs,
                error=str(exc),
                error_detail={"status_code": status_code, "body": body},
                decision={
                    "recommended_action": "inspect",
                    "reason": (
                        "The loop stopped on a transport or auth error. It does NOT retry "
                        "on its own: a request budget cannot bound a loop that retries "
                        "errors it cannot classify."
                    ),
                },
                next_actions=["inspect"],
                compensation={"available": False},
            ),
            human=human,
        )
        raise typer.Exit(code=1) from exc

    ok = bool(journal["ok"])
    spend = journal["spend"]
    evidence = [
        evidence_assertion(
            "acquisition-loop:stop-reason",
            value=journal["stop_reason"],
            passed=ok,
            note=journal["stop_detail"],
        ),
        evidence_count(
            "acquisition-loop:attempts-made",
            value=spend["attempts_made"],
            passed=spend["attempts_made"] <= budget.max_attempts,
            note=f"Attempt budget {budget.max_attempts}.",
        ),
        evidence_count(
            "acquisition-loop:upstream-requests-authorised",
            value=spend["upstream_requests_authorised"],
            passed=spend["upstream_requests_authorised"] <= budget.max_upstream_requests,
            note=(
                f"Ceiling {budget.max_upstream_requests} across the whole loop. Declared "
                "cost per attempt, reconciled upward against captured counts — "
                "platform-control does not report actual upstream request counts."
            ),
        ),
        evidence_assertion(
            "acquisition-loop:actor",
            value=journal["actor"],
            passed=journal["actor"] == "agent",
            note=f"ADR-0038: recorded as an agent ({journal['agent_id']}), never a person.",
        ),
    ]

    if journal["stop_reason"] == STOP_EVIDENCE_CAPTURED:
        decision = {
            "recommended_action": "needs-human",
            "reason": (
                "Acceptance evidence captured. Flipping `enabled: true` is the second "
                "ADR-0030 key and belongs to a person — `evidara workflow coverage "
                "enable`."
            ),
        }
        status = "passed"
    elif journal["stop_reason"] == STOP_REFUSED:
        decision = {"recommended_action": "needs-human", "reason": journal["stop_detail"]}
        status = "needs_human"
    else:
        decision = {"recommended_action": "needs-human", "reason": journal["stop_detail"]}
        status = "needs_human" if not ok else "passed"

    last_run = next(
        (a.get("run_id") for a in reversed(journal["attempts"]) if a.get("run_id")), None
    )
    _emit(
        build_envelope(
            ok=ok,
            workflow=_WORKFLOW,
            step=_STEP,
            run_id=last_run,
            status=status,
            side_effect_level="none" if preflight_only else "reversible",
            inputs=inputs,
            artifacts={"journal": journal},
            evidence=evidence,
            decision=decision,
            next_actions=["inspect"] if not ok else ["enable"],
            compensation={"available": False},
        ),
        human=human,
    )
    if not ok:
        raise typer.Exit(code=1)
