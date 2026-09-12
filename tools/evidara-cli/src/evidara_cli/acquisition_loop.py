"""The acquisition loop an agent may drive — launch, observe, stop — within a budget.

#980. Every step of an acquisition already exists as an endpoint (`GET /v1/runs/readiness`,
`POST /v1/runs`, `GET /v1/runs/{id}/pipeline-health`, `POST /v1/runs/{id}/cancel`) and the
decision layer above them exists too (:mod:`evidara_cli.agent_loop`, #909). What did not
exist is the thing that *composes* them without being dangerous.

This module is that composition, and it is deliberately the boring half: a pure state
machine over an injected client, so the branching can be unit-tested without a stack and
without a portal — the same rule :mod:`evidara_cli.coverage` and :mod:`evidara_cli.agent_loop`
already follow. The HTTP half is :mod:`evidara_cli.acquisition_loop_cmd`.

## The budget is the feature, not the loop

The loop itself is twenty lines. What makes it shippable is that it cannot run away. The
2026-09-10 Zürich acquisition made **944 requests in 36 seconds** against a live cantonal
government portal. "Retry until it works" around that is a denial-of-service against a
public registry, authored by us, and no server-side check would call it anything but
traffic.

So three bounds, each with its own guard test:

1. **A per-source attempt budget.** `LoopBudget.max_attempts` — N launches, then stop and
   report. There is no unlimited: the dataclass refuses a non-positive or absent value at
   construction rather than treating it as "no limit".
2. **A ceiling on total upstream requests across the whole loop** — not per attempt, which
   is the bound that does not bind. An attempt is *pre-authorised*: the loop charges its
   declared cost before launching and refuses to launch one that would breach the ceiling.
3. **Backoff between attempts**, exponential, capped.

### What the ceiling can and cannot be measured against (read this before trusting it)

**platform-control does not report how many upstream requests a run made.** Providers
compute an `estimated_request_count` when they plan
(`platform-control/src/acquisition_core/providers.py:98`) and it is never persisted and
never serialised — it appears in no response model and nowhere in
`contracts/api/platform-control.openapi.yaml`. `RunResponse`
(`platform-control/src/platform_control/schemas/run.py:89-144`) carries
`artifacts_count` and `captured_resources_count`, which are *outcomes*, not request
counts: a crawl that fetches 900 pages and captures 12 reports 12.

So this ceiling bounds **what the loop authorises**, not what the portal actually served.
It is honest about that in two ways rather than pretending otherwise:

- the per-attempt cost is *declared by the caller* (`declared_requests_per_attempt`), who
  knows the spec's `limit` / `max_pages` / seed count — it is not re-derived here, because
  that derivation lives in the providers and a second copy in a CLI is exactly the
  duplicated rule AGENTS.md warns about; and
- it is **reconciled upward, never downward**, after each attempt: if a run captured more
  resources than the declared cost, the observed lower bound is charged instead
  (:func:`observed_request_floor`). An attempt that turns out costlier than declared eats
  more of the ceiling; an attempt that looks cheap never refunds one.

Making this exact needs a server-side counter on the run. That is a contract change and is
named as follow-up work in the PR, not smuggled in here.

## Refusals are terminal, and that can only be enforced here

:mod:`evidara_cli.agent_loop` states the rule: *"a refusal is an outcome the agent reports,
never an obstacle it works around… an agent that retried it would be overriding a human by
persistence rather than by permission, and no server-side check would see anything but a
normal request."*

That is the whole reason this module treats a refusal as a hard stop in three places — the
pre-flight readiness verdict, the launch response (`refused` / `refusal_code`), and the
stall diagnosis (`run_refused_by_lock`) — and why
`test_a_refusal_is_terminal_with_attempts_and_ceiling_still_unspent` fails if any of the three
is softened to a retry. The server cannot catch it: a retried refusal is an ordinary
request.

## What the loop may retry, and why the list is one item long

Only a run that **failed on its own terms** (`STALL_RUN_FAILED`). Everything else is either
a decision (refusal), an environment defect that another run cannot fix (no dispatch
worker, publish path on `noop`), or downstream backlog where re-running acquisition *adds*
captures to a queue rather than clearing it — the same reasoning that makes
`AWAIT_PIPELINE` not a run in `agent_loop`.

**Adjusting the spec is deliberately not in the loop.** `POST /v1/sources/{id}/versions` is
reachable and the loop does not call it: a new spec is precisely the thing a request budget
cannot bound, because the declared per-attempt cost the ceiling is charged against was
stated for the *old* spec. An agent that rewrites the spec and retries has silently left
its own budget behind. The loop reports the diagnosis and stops; a person authors the new
version.

## Attribution (ADR-0038)

Every call the loop makes is stamped as an agent and never as a person. ADR-0038 exists to
end a non-person appearing as one ("Relabel, don't rewrite"), and per-person identity does
not exist yet — there is no `actor` field on `CreateRunRequest`
(`platform-control/src/platform_control/schemas/run.py:79-86`), so the only attribution
channel available today is the correlation id, which this module gives an unmistakable
`agent:` prefix. The journal records `actor: "agent"` and the agent id, and never accepts a
human name: there is no parameter through which one could be passed.
"""

from __future__ import annotations

import uuid
from dataclasses import dataclass, field
from typing import Any, Protocol

from evidara_cli.coverage import (
    MODE_ACCEPTANCE,
    STALL_RUN_FAILED,
    STALL_RUN_REFUSED,
    STALL_TOO_EARLY,
    STALL_UNKNOWN,
    TERMINAL_RUN_STATUSES,
    acceptance_evidence_verdict,
    diagnose_stall,
)

#: Attribution actor. A constant, not a parameter — see the module docstring.
AGENT_ACTOR = "agent"
DEFAULT_AGENT_ID = "evidara-cli/acquisition-loop"
#: Prefix on every correlation id the loop mints, so a run driven by this loop is
#: identifiable in platform-control's logs without asking anyone what they were doing.
CORRELATION_PREFIX = "agent"

# --- Stop reasons ----------------------------------------------------------------
STOP_EVIDENCE_CAPTURED = "acceptance_evidence_captured"
STOP_REFUSED = "refused"
STOP_ATTEMPT_BUDGET_EXHAUSTED = "attempt_budget_exhausted"
STOP_REQUEST_CEILING_REACHED = "request_ceiling_reached"
STOP_NEEDS_HUMAN = "needs_human"
STOP_UNDIAGNOSED = "undiagnosed"
STOP_POLL_BUDGET_EXHAUSTED = "poll_budget_exhausted"

#: The only outcome the loop may answer with another run. See the module docstring for
#: why every other cause is a stop rather than a retry. Widening this set is the change
#: that needs the most argument in review.
AGENT_RETRYABLE_CAUSES: frozenset[str] = frozenset({STALL_RUN_FAILED})

_STOP_DETAIL = {
    STOP_EVIDENCE_CAPTURED: (
        "The run completed and earns ADR-0030 acceptance evidence. The loop stops here: "
        "flipping `enabled: true` is a human's key (#854) and no action in this module "
        "approaches it."
    ),
    STOP_REFUSED: (
        "A refusal is an outcome to report, never an obstacle to work around. The loop "
        "stops with attempts and request budget still unspent, deliberately — retrying "
        "would override a human by persistence rather than by permission, and the server "
        "would see only ordinary requests."
    ),
    STOP_ATTEMPT_BUDGET_EXHAUSTED: (
        "The per-source attempt budget is spent. Stopping and reporting is the failure "
        "mode; persistence is not."
    ),
    STOP_REQUEST_CEILING_REACHED: (
        "The next attempt's declared cost would breach the loop's total upstream-request "
        "ceiling, so it was never launched. The ceiling bounds what the loop authorises "
        "against a live portal across the whole loop, not per attempt."
    ),
    STOP_NEEDS_HUMAN: (
        "The diagnosis names a cause another run cannot fix — an environment defect, or "
        "downstream backlog where re-running acquisition adds captures rather than "
        "clearing them. Re-running would spend a portal's capacity to learn nothing."
    ),
    STOP_UNDIAGNOSED: (
        "No cause could be named. That is not a clean bill of health (ADR-0052) and it is "
        "not a licence to retry either: an unexplained failure repeated is an unexplained "
        "failure repeated."
    ),
    STOP_POLL_BUDGET_EXHAUSTED: (
        "The run did not reach a terminal state within the attempt's poll budget, so the "
        "loop cancelled it rather than leaving load running at the portal unattended."
    ),
}


class BudgetError(ValueError):
    """A budget that does not bound anything. Raised at construction, never survived."""


@dataclass(frozen=True)
class LoopBudget:
    """What the loop is allowed to spend. Every field bounds something.

    There is no sentinel for "unlimited" and no default that means one: a missing or
    non-positive bound raises :class:`BudgetError` at construction. The alternative —
    treating ``0``/``None`` as "no limit" — is how an unbounded loop ships looking
    configured.
    """

    declared_requests_per_attempt: int
    """The caller's stated worst-case upstream request count for ONE attempt of this
    source. Charged before the attempt launches; reconciled upward afterwards if the run
    captured more than this. Not derived here — see the module docstring."""

    max_attempts: int = 3
    """Launches for this source, across the whole loop."""

    max_upstream_requests: int = 1000
    """Ceiling on authorised upstream requests across the WHOLE loop."""

    backoff_seconds: float = 30.0
    backoff_factor: float = 2.0
    max_backoff_seconds: float = 300.0

    poll_interval_seconds: float = 5.0
    max_polls_per_attempt: int = 120
    """A bound on observation, not on the portal: polls hit platform-control, not the
    source. It exists so an attempt that never terminates is cancelled rather than
    watched forever."""

    def __post_init__(self) -> None:
        for name in ("declared_requests_per_attempt", "max_attempts", "max_upstream_requests"):
            value = getattr(self, name)
            if not isinstance(value, int) or isinstance(value, bool) or value < 1:
                raise BudgetError(
                    f"{name} must be a positive integer; got {value!r}. There is no "
                    "unlimited setting — an acquisition loop without a bound is a "
                    "denial-of-service against a public registry (#980)."
                )
        if self.max_polls_per_attempt < 1:
            raise BudgetError("max_polls_per_attempt must be >= 1")
        for name in ("backoff_seconds", "backoff_factor", "max_backoff_seconds"):
            if getattr(self, name) < 0:
                raise BudgetError(f"{name} must not be negative")
        if self.declared_requests_per_attempt > self.max_upstream_requests:
            raise BudgetError(
                "declared_requests_per_attempt exceeds max_upstream_requests, so no "
                "attempt could ever be authorised. State a budget the loop can act "
                "within rather than one that stops before it starts."
            )

    def backoff_for(self, attempts_already_made: int) -> float:
        """Seconds to wait before the attempt following ``attempts_already_made``."""
        delay = self.backoff_seconds * (self.backoff_factor ** max(0, attempts_already_made - 1))
        return min(delay, self.max_backoff_seconds)

    def as_dict(self) -> dict[str, Any]:
        return {
            "max_attempts": self.max_attempts,
            "max_upstream_requests": self.max_upstream_requests,
            "declared_requests_per_attempt": self.declared_requests_per_attempt,
            "backoff_seconds": self.backoff_seconds,
            "backoff_factor": self.backoff_factor,
            "max_backoff_seconds": self.max_backoff_seconds,
            "poll_interval_seconds": self.poll_interval_seconds,
            "max_polls_per_attempt": self.max_polls_per_attempt,
        }


class LoopClient(Protocol):
    """The four endpoints the loop drives, plus sleeping — and nothing else.

    Deliberately narrow: this protocol is the loop's entire reach into the platform, so
    what it *cannot* do is readable in five signatures. There is no method that writes a
    source version (the loop does not adjust specs) and none that touches enablement
    (`PUT …/enablement` is a human's key, #854).
    """

    def readiness(self, *, source_id: str, source_version_id: str, mode: str) -> dict[str, Any]:
        """`GET /v1/runs/readiness`."""

    def launch(
        self, *, source_id: str, source_version_id: str, mode: str, correlation_id: str
    ) -> dict[str, Any]:
        """`POST /v1/runs`."""

    def poll(self, run_id: str) -> tuple[dict[str, Any], dict[str, Any]]:
        """`GET /v1/runs/{id}` joined with `GET /v1/runs/{id}/pipeline-health`."""

    def cancel(self, run_id: str) -> dict[str, Any]:
        """`POST /v1/runs/{id}/cancel`."""

    def sleep(self, seconds: float) -> None:
        """Backoff. Injected so tests drive the loop without waiting."""


@dataclass
class _Ledger:
    """Budget accounting, in one place so the stop conditions cannot disagree."""

    budget: LoopBudget
    attempts_made: int = 0
    upstream_requests_authorised: int = 0
    reconciled_overruns: list[dict[str, int]] = field(default_factory=list)

    def attempts_remaining(self) -> int:
        return max(0, self.budget.max_attempts - self.attempts_made)

    def requests_remaining(self) -> int:
        return max(0, self.budget.max_upstream_requests - self.upstream_requests_authorised)

    def next_attempt_would_breach_ceiling(self) -> bool:
        cost = self.budget.declared_requests_per_attempt
        return self.upstream_requests_authorised + cost > self.budget.max_upstream_requests

    def authorise_attempt(self) -> None:
        self.attempts_made += 1
        self.upstream_requests_authorised += self.budget.declared_requests_per_attempt

    def reconcile(self, *, attempt: int, observed_floor: int) -> None:
        """Charge an attempt that cost more than declared. Never refunds one that cost less.

        A downward reconciliation would let a loop that under-runs its declared cost buy
        extra attempts, which is the ceiling paying for its own erosion.
        """
        extra = observed_floor - self.budget.declared_requests_per_attempt
        if extra > 0:
            self.upstream_requests_authorised += extra
            self.reconciled_overruns.append(
                {"attempt": attempt, "observed_floor": observed_floor, "extra_charged": extra}
            )

    def as_dict(self) -> dict[str, Any]:
        return {
            "attempts_made": self.attempts_made,
            "attempts_remaining": self.attempts_remaining(),
            "upstream_requests_authorised": self.upstream_requests_authorised,
            "upstream_requests_remaining": self.requests_remaining(),
            "reconciled_overruns": list(self.reconciled_overruns),
        }


def agent_attribution(
    *, agent_id: str = DEFAULT_AGENT_ID, correlation_id: str | None = None
) -> dict[str, str]:
    """How this loop identifies itself. ADR-0038: as an agent, never as a person.

    There is no parameter for a human here, and that absence is the guard: attribution
    cannot be handed a person's name by a caller who finds it convenient.
    """
    cid = correlation_id or f"{CORRELATION_PREFIX}:{uuid.uuid4().hex[:16]}"
    if not cid.startswith(f"{CORRELATION_PREFIX}:"):
        cid = f"{CORRELATION_PREFIX}:{cid}"
    return {"actor": AGENT_ACTOR, "agent_id": agent_id, "correlation_id": cid}


def readiness_refusals(readiness: dict[str, Any]) -> list[dict[str, str]]:
    """The checks that refuse this dispatch, as codes rather than prose.

    A readiness payload with no `checks` and no `ready` is not evidence of readiness —
    it is an unreadable answer, and this fails closed on it.
    """
    checks = readiness.get("checks")
    failed = [
        {"code": str(c.get("code") or "unknown_check"), "detail": str(c.get("detail") or "")}
        for c in (checks or [])
        if isinstance(c, dict) and not c.get("ok")
    ]
    if failed:
        return failed
    if readiness.get("ready") is True:
        return []
    return [
        {
            "code": "readiness_unreadable",
            "detail": (
                "The readiness payload did not say `ready: true` and named no failing "
                "check. Unreadable is not ready."
            ),
        }
    ]


def run_is_refused(run: dict[str, Any]) -> bool:
    """Whether this run is a refusal record.

    Reads `refused` first — `refusal_code` is absent on refusals recorded before #908, so
    an absent code means "not classified", never "not refused"
    (`platform-control/src/platform_control/schemas/run.py:111-122`).
    """
    if bool(run.get("refused")):
        return True
    return bool(run.get("refusal_code"))


def observed_request_floor(run: dict[str, Any]) -> int:
    """A LOWER BOUND on the upstream requests an attempt made.

    `captured_resources_count` and `artifacts_count` are outcomes, not request counts: a
    crawl that fetched 900 pages and kept 12 reports 12. The larger of the two is
    therefore the most this snapshot can honestly claim, and it is used only to charge
    *more* than the declared cost, never less.
    """
    counts = [run.get("captured_resources_count"), run.get("artifacts_count")]
    return max(
        (int(c) for c in counts if isinstance(c, int) and not isinstance(c, bool) and c > 0),
        default=0,
    )


def _stop(
    reason: str,
    *,
    ok: bool,
    ledger: _Ledger,
    attempts: list[dict[str, Any]],
    attribution: dict[str, str],
    detail: str | None = None,
    refusals: list[dict[str, str]] | None = None,
    diagnosis: dict[str, Any] | None = None,
    evidence_verdict: dict[str, Any] | None = None,
) -> dict[str, Any]:
    return {
        "ok": ok,
        "stop_reason": reason,
        "stop_detail": detail or _STOP_DETAIL[reason],
        # Recorded on every journal, not only on the refusal path: "the loop stopped and
        # who it was" is the part a person reads afterwards (ADR-0038).
        "actor": attribution["actor"],
        "agent_id": attribution["agent_id"],
        "correlation_id": attribution["correlation_id"],
        "budget": ledger.budget.as_dict(),
        "spend": ledger.as_dict(),
        "attempts": attempts,
        "refusals": refusals or [],
        "diagnosis": diagnosis,
        "acceptance_evidence": evidence_verdict,
    }


def _poll_attempt(
    client: LoopClient, run_id: str, budget: LoopBudget
) -> tuple[dict[str, Any], dict[str, Any], int, bool]:
    """Poll one attempt to terminal. Returns (run, health, polls, reached_terminal)."""
    run: dict[str, Any] = {}
    health: dict[str, Any] = {}
    polls = 0
    while polls < budget.max_polls_per_attempt:
        polls += 1
        run, health = client.poll(run_id)
        run = run if isinstance(run, dict) else {}
        health = health if isinstance(health, dict) else {}
        if run_is_refused(run):
            return run, health, polls, True
        if str(run.get("status") or "").lower() in TERMINAL_RUN_STATUSES:
            return run, health, polls, True
        if polls < budget.max_polls_per_attempt:
            client.sleep(budget.poll_interval_seconds)
    return run, health, polls, False


def drive_acquisition(
    *,
    client: LoopClient,
    source_id: str,
    source_version_id: str,
    budget: LoopBudget,
    agent_id: str = DEFAULT_AGENT_ID,
    correlation_id: str | None = None,
) -> dict[str, Any]:
    """Drive one source to acceptance evidence, a refusal, or an exhausted budget.

    Returns a journal: what it did, what it spent, why it stopped. The journal is the
    deliverable — a loop whose failure mode is "stopping and saying why" has to say why
    somewhere a person can read it afterwards.

    Never raises on a platform answer it does not like; it stops and reports. Exceptions
    from the client (transport, auth) propagate to the caller, which owns the envelope.
    """
    attribution = agent_attribution(agent_id=agent_id, correlation_id=correlation_id)
    ledger = _Ledger(budget=budget)
    attempts: list[dict[str, Any]] = []

    while True:
        # --- bound 1: attempts ---------------------------------------------------
        if ledger.attempts_remaining() <= 0:
            return _stop(
                STOP_ATTEMPT_BUDGET_EXHAUSTED,
                ok=False,
                ledger=ledger,
                attempts=attempts,
                attribution=attribution,
            )
        # --- bound 2: total upstream requests ------------------------------------
        # Checked BEFORE the attempt, against its declared cost. A ceiling consulted
        # after the fact is a report, not a bound.
        if ledger.next_attempt_would_breach_ceiling():
            return _stop(
                STOP_REQUEST_CEILING_REACHED,
                ok=False,
                ledger=ledger,
                attempts=attempts,
                attribution=attribution,
            )

        attempt_no = ledger.attempts_made + 1
        record: dict[str, Any] = {"attempt": attempt_no, "actor": attribution["actor"]}

        # --- pre-flight: a refusal here is terminal ------------------------------
        readiness = client.readiness(
            source_id=source_id,
            source_version_id=source_version_id,
            mode=MODE_ACCEPTANCE,
        )
        readiness = readiness if isinstance(readiness, dict) else {}
        refusals = readiness_refusals(readiness)
        record["readiness"] = readiness
        if refusals:
            record["outcome"] = STOP_REFUSED
            attempts.append(record)
            return _stop(
                STOP_REFUSED,
                ok=False,
                ledger=ledger,
                attempts=attempts,
                attribution=attribution,
                refusals=refusals,
            )

        # --- launch ---------------------------------------------------------------
        ledger.authorise_attempt()
        run = client.launch(
            source_id=source_id,
            source_version_id=source_version_id,
            mode=MODE_ACCEPTANCE,
            correlation_id=attribution["correlation_id"],
        )
        run = run if isinstance(run, dict) else {}
        run_id = str(run.get("run_id") or "")
        record["run_id"] = run_id

        if run_is_refused(run):
            record["outcome"] = STOP_REFUSED
            record["run"] = run
            attempts.append(record)
            return _stop(
                STOP_REFUSED,
                ok=False,
                ledger=ledger,
                attempts=attempts,
                attribution=attribution,
                refusals=[
                    {
                        "code": str(run.get("refusal_code") or "refused_without_code"),
                        "detail": str(run.get("failure_reason") or ""),
                    }
                ],
            )

        # --- observe --------------------------------------------------------------
        run, health, polls, reached = _poll_attempt(client, run_id, budget)
        record["polls"] = polls
        record["run"] = run
        ledger.reconcile(attempt=attempt_no, observed_floor=observed_request_floor(run))

        if not reached:
            # Stopping is part of the loop's duty: an attempt it can no longer observe
            # is load it is no longer accounting for.
            record["cancelled"] = True
            record["outcome"] = STOP_POLL_BUDGET_EXHAUSTED
            client.cancel(run_id)
            attempts.append(record)
            return _stop(
                STOP_POLL_BUDGET_EXHAUSTED,
                ok=False,
                ledger=ledger,
                attempts=attempts,
                attribution=attribution,
            )

        if run_is_refused(run):
            record["outcome"] = STOP_REFUSED
            attempts.append(record)
            return _stop(
                STOP_REFUSED,
                ok=False,
                ledger=ledger,
                attempts=attempts,
                attribution=attribution,
                refusals=[
                    {
                        "code": str(run.get("refusal_code") or "refused_without_code"),
                        "detail": str(run.get("failure_reason") or ""),
                    }
                ],
            )

        # --- did it earn evidence? -------------------------------------------------
        verdict = acceptance_evidence_verdict(run=run)
        record["acceptance_evidence"] = verdict
        if verdict["is_acceptance_evidence"]:
            record["outcome"] = STOP_EVIDENCE_CAPTURED
            attempts.append(record)
            return _stop(
                STOP_EVIDENCE_CAPTURED,
                ok=True,
                ledger=ledger,
                attempts=attempts,
                attribution=attribution,
                evidence_verdict=verdict,
            )

        # --- diagnose, then decide whether another run could possibly help ---------
        diagnosis = diagnose_stall(run, health)
        record["diagnosis"] = diagnosis
        cause = diagnosis["cause"]

        if cause == STALL_RUN_REFUSED:
            record["outcome"] = STOP_REFUSED
            attempts.append(record)
            return _stop(
                STOP_REFUSED,
                ok=False,
                ledger=ledger,
                attempts=attempts,
                attribution=attribution,
                diagnosis=diagnosis,
                refusals=[{"code": STALL_RUN_REFUSED, "detail": diagnosis["detail"]}],
            )

        if cause not in AGENT_RETRYABLE_CAUSES:
            # `too_early` lands here too: the poll loop only exits on terminal, so a
            # terminal run diagnosed as still-in-flight is a contradiction to report,
            # not a reason to launch another run.
            reason = (
                STOP_UNDIAGNOSED
                if cause in {STALL_UNKNOWN, STALL_TOO_EARLY}
                else (STOP_NEEDS_HUMAN)
            )
            record["outcome"] = reason
            attempts.append(record)
            return _stop(
                reason,
                ok=False,
                ledger=ledger,
                attempts=attempts,
                attribution=attribution,
                diagnosis=diagnosis,
            )

        record["outcome"] = "retryable"
        attempts.append(record)
        if ledger.attempts_remaining() > 0 and not ledger.next_attempt_would_breach_ceiling():
            delay = budget.backoff_for(ledger.attempts_made)
            record["backoff_seconds"] = delay
            client.sleep(delay)
