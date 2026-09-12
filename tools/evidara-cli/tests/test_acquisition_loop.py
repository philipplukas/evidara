"""The acquisition loop's bounds, and the fixtures that make each bound falsifiable (#980).

Three guards carry this module, and each one has a fixture in which an *unbounded*
implementation behaves differently — that is the whole difficulty of testing a budget. A
loop that never retries passes every budget assertion vacuously, so every budget test
below drives a source that fails repeatedly and asserts the loop stopped at N and **not**
at N+1:

- `test_the_attempt_budget_stops_at_n_and_not_n_plus_one`
- `test_the_request_ceiling_stops_the_loop_before_the_attempt_budget_does`
- `test_an_attempt_that_overran_its_declared_cost_is_charged_what_it_cost`
- `test_a_refusal_is_terminal_with_attempts_and_ceiling_still_unspent`

`FakeLoopClient` repeats its last scripted outcome forever and raises past a hard cap, so
an unbounded loop fails these tests loudly instead of hanging.
"""

from __future__ import annotations

import ast
import inspect
from typing import Any

import pytest

from evidara_cli import acquisition_loop
from evidara_cli.acquisition_loop import (
    AGENT_RETRYABLE_CAUSES,
    CORRELATION_PREFIX,
    STOP_ATTEMPT_BUDGET_EXHAUSTED,
    STOP_EVIDENCE_CAPTURED,
    STOP_NEEDS_HUMAN,
    STOP_POLL_BUDGET_EXHAUSTED,
    STOP_REFUSED,
    STOP_REQUEST_CEILING_REACHED,
    BudgetError,
    LoopBudget,
    LoopClient,
    agent_attribution,
    drive_acquisition,
    observed_request_floor,
    readiness_refusals,
)
from evidara_cli.coverage import STALL_RUN_REFUSED

# A cap far above any budget under test. Reaching it means the loop did not stop.
RUNAWAY_CAP = 50


def _code_without_prose(module: Any) -> str:
    """The module's source with every docstring removed.

    The source-scanning guards below must read what the module *does*, not what it
    *says*. This module's docstrings name `PUT …/enablement` and
    `POST /v1/sources/{id}/versions` precisely to explain why the loop does not call
    them, and a scan that could not tell the two apart would force the explanation out
    of the code — which is how the reasoning gets lost. `agent_loop.py`'s equivalent
    guard makes the same distinction in a comment.
    """
    source = inspect.getsource(module)
    for node in ast.walk(ast.parse(source)):
        if (
            isinstance(node, ast.Expr)
            and isinstance(node.value, ast.Constant)
            and isinstance(node.value.value, str)
        ):
            source = source.replace(node.value.value, "", 1)
    return source


def _called_names(module: Any) -> set[str]:
    """Every function, method and attribute name the module reaches for."""
    names: set[str] = set()
    for node in ast.walk(ast.parse(inspect.getsource(module))):
        if isinstance(node, ast.Attribute):
            names.add(node.attr)
        elif isinstance(node, ast.Call) and isinstance(node.func, ast.Name):
            names.add(node.func.id)
    return names


class LoopRanAway(AssertionError):
    """Raised when the loop launches past every budget under test."""


READY = {
    "source_id": "src_zh",
    "source_version_id": "sv_zh_1",
    "mode": "acceptance",
    "ready": True,
    "checks": [
        {"code": "acquisition_lock_open", "ok": True, "detail": "Acceptance run."},
        {"code": "source_version_approved", "ok": True, "detail": "Approved."},
    ],
}

REFUSED_PREFLIGHT = {
    "source_id": "src_zh",
    "source_version_id": "sv_zh_1",
    "mode": "acceptance",
    "ready": False,
    "checks": [
        {
            "code": "acquisition_lock_open",
            "ok": False,
            "detail": "An operator explicitly turned the config key off.",
        }
    ],
}


def _run(
    run_id: str = "run_1",
    *,
    status: str = "completed",
    mode: str = "acceptance",
    captured: int = 12,
    refused: bool = False,
    refusal_code: str | None = None,
    failure_reason: str | None = None,
    artifacts: int | None = None,
) -> dict[str, Any]:
    return {
        "run_id": run_id,
        "status": status,
        "mode": mode,
        "captured_resources_count": captured,
        "artifacts_count": captured if artifacts is None else artifacts,
        "refused": refused,
        "refusal_code": refusal_code,
        "failure_reason": failure_reason,
    }


def _health(
    *,
    overall: str = "ok",
    processing_events: int = 3,
    lifecycle_events: int = 3,
    stages: list[dict[str, Any]] | None = None,
) -> dict[str, Any]:
    return {
        "overall_status": overall,
        "processing_status_event_count": processing_events,
        "document_lifecycle_event_count": lifecycle_events,
        "stages": stages
        or [
            {"stage": "acquisition", "status": "ok"},
            {"stage": "document_intelligence", "status": "ok"},
            {"stage": "projection", "status": "ok"},
            {"stage": "search", "status": "ok"},
        ],
    }


class FakeLoopClient:
    """A scripted platform-control. Repeats its last outcome so a runaway loop is visible.

    Each outcome is ``{"launch": run, "polls": [(run, health), ...]}``. The launch run is
    what `POST /v1/runs` returned; the polls are what `GET /v1/runs/{id}` and
    `…/pipeline-health` return in order, the last repeating.
    """

    def __init__(
        self,
        *,
        readiness_payload: dict[str, Any] | None = None,
        outcomes: list[dict[str, Any]] | None = None,
    ) -> None:
        self.readiness_payload = readiness_payload if readiness_payload is not None else READY
        self.outcomes = outcomes or []
        self.launches: list[dict[str, Any]] = []
        self.readiness_calls = 0
        self.polls: list[str] = []
        self.cancels: list[str] = []
        self.sleeps: list[float] = []

    def readiness(self, *, source_id: str, source_version_id: str, mode: str) -> dict[str, Any]:
        self.readiness_calls += 1
        assert mode == "acceptance", "the loop may only ever launch acceptance runs"
        return self.readiness_payload

    def _outcome(self, index: int) -> dict[str, Any]:
        if not self.outcomes:
            raise LoopRanAway("the loop launched a run with no scripted outcome")
        return self.outcomes[min(index, len(self.outcomes) - 1)]

    def launch(
        self, *, source_id: str, source_version_id: str, mode: str, correlation_id: str
    ) -> dict[str, Any]:
        if len(self.launches) >= RUNAWAY_CAP:
            raise LoopRanAway(
                f"the loop launched {RUNAWAY_CAP} runs — no budget stopped it. Against a "
                "live portal this is the 944-requests-in-36-seconds incident, repeated."
            )
        self.launches.append({"mode": mode, "correlation_id": correlation_id})
        return self._outcome(len(self.launches) - 1)["launch"]

    def poll(self, run_id: str) -> tuple[dict[str, Any], dict[str, Any]]:
        self.polls.append(run_id)
        polls = self._outcome(len(self.launches) - 1)["polls"]
        if not polls:
            # An outcome with no polls is a refusal the launch call itself returned.
            # Polling it is the bug under test, not a scripting gap.
            raise LoopRanAway(f"the loop polled {run_id!r}, a dispatch that was refused at launch")
        index = min(self.polls.count(run_id) - 1, len(polls) - 1)
        return polls[index]

    def cancel(self, run_id: str) -> dict[str, Any]:
        self.cancels.append(run_id)
        return {"run_id": run_id, "status": "cancelled"}

    def sleep(self, seconds: float) -> None:
        self.sleeps.append(seconds)


def _budget(**overrides: Any) -> LoopBudget:
    kwargs: dict[str, Any] = {
        "declared_requests_per_attempt": 100,
        "max_attempts": 3,
        "max_upstream_requests": 1000,
        "backoff_seconds": 30.0,
        "backoff_factor": 2.0,
        "max_backoff_seconds": 300.0,
        "poll_interval_seconds": 0.0,
        "max_polls_per_attempt": 5,
    }
    kwargs.update(overrides)
    return LoopBudget(**kwargs)


def _drive(client: FakeLoopClient, budget: LoopBudget) -> dict[str, Any]:
    return drive_acquisition(
        client=client,
        source_id="src_zh",
        source_version_id="sv_zh_1",
        budget=budget,
    )


def _failing_outcome(run_id: str = "run_fail", captured: int = 0) -> dict[str, Any]:
    """A run that failed on its own terms — the ONE cause the loop may answer with a retry."""
    run = _run(
        run_id,
        status="failed",
        captured=captured,
        failure_reason="portal returned 503 for 4 of 6 seed urls",
    )
    return {"launch": _run(run_id, status="pending", captured=0), "polls": [(run, _health())]}


# ---------------------------------------------------------------------------------
# The happy path exists so the budget guards cannot be satisfied by refusing everything
# ---------------------------------------------------------------------------------


def test_a_run_that_earns_evidence_stops_the_loop_immediately() -> None:
    client = FakeLoopClient(
        outcomes=[
            {
                "launch": _run("run_ok", status="pending", captured=0),
                "polls": [(_run("run_ok", status="completed", captured=12), _health())],
            }
        ]
    )
    journal = _drive(client, _budget())

    assert journal["ok"] is True
    assert journal["stop_reason"] == STOP_EVIDENCE_CAPTURED
    assert len(client.launches) == 1
    assert journal["spend"]["attempts_made"] == 1
    assert journal["acceptance_evidence"]["is_acceptance_evidence"] is True
    # Having evidence does NOT mean the loop turns the key.
    assert journal["spend"]["attempts_remaining"] == 2


# ---------------------------------------------------------------------------------
# Bound 1 — the attempt budget
# ---------------------------------------------------------------------------------


@pytest.mark.parametrize("max_attempts", [1, 2, 3, 5])
def test_the_attempt_budget_stops_at_n_and_not_n_plus_one(max_attempts: int) -> None:
    """The fixture fails forever. An unbounded loop hits `LoopRanAway`; this stops at N.

    Parameterised deliberately: a loop hard-coded to "three tries" passes a single-value
    test and is not a budget.
    """
    client = FakeLoopClient(outcomes=[_failing_outcome()])
    journal = _drive(client, _budget(max_attempts=max_attempts, max_upstream_requests=100_000))

    assert len(client.launches) == max_attempts
    assert journal["stop_reason"] == STOP_ATTEMPT_BUDGET_EXHAUSTED
    assert journal["ok"] is False
    assert journal["spend"]["attempts_made"] == max_attempts
    assert journal["spend"]["attempts_remaining"] == 0


def test_the_loop_backs_off_between_attempts_and_the_backoff_grows() -> None:
    """Three attempts means two waits, not zero — and the second is longer than the first."""
    client = FakeLoopClient(outcomes=[_failing_outcome()])
    _drive(
        client,
        _budget(
            max_attempts=3,
            max_upstream_requests=100_000,
            backoff_seconds=30.0,
            backoff_factor=2.0,
            poll_interval_seconds=0.0,
        ),
    )
    # poll_interval 0.0 still sleeps between polls, so filter to the backoff waits.
    backoffs = [s for s in client.sleeps if s > 0]
    assert backoffs == [30.0, 60.0]


def test_the_backoff_is_capped() -> None:
    budget = _budget(backoff_seconds=100.0, backoff_factor=10.0, max_backoff_seconds=250.0)
    assert budget.backoff_for(1) == 100.0
    assert budget.backoff_for(2) == 250.0
    assert budget.backoff_for(9) == 250.0


# ---------------------------------------------------------------------------------
# Bound 2 — the total upstream-request ceiling
# ---------------------------------------------------------------------------------


def test_the_request_ceiling_stops_the_loop_before_the_attempt_budget_does() -> None:
    """The ceiling is across the WHOLE loop, which is the bound a per-attempt cap misses.

    Ten attempts are authorised and each declares 400 requests against a 1000 ceiling, so
    the third attempt is never launched. A loop that only checked a per-attempt limit
    would launch all ten — 4000 requests at the portal.
    """
    client = FakeLoopClient(outcomes=[_failing_outcome()])
    journal = _drive(
        client,
        _budget(max_attempts=10, declared_requests_per_attempt=400, max_upstream_requests=1000),
    )

    assert len(client.launches) == 2
    assert journal["stop_reason"] == STOP_REQUEST_CEILING_REACHED
    assert journal["spend"]["upstream_requests_authorised"] == 800
    # Attempts were still available: the ceiling, not the attempt budget, stopped it.
    assert journal["spend"]["attempts_remaining"] == 8


def test_an_attempt_that_overran_its_declared_cost_is_charged_what_it_cost() -> None:
    """Reconciliation is upward-only, and it changes when the loop stops.

    Declared 100 against a 250 ceiling: on declared cost alone two attempts fit. The run
    captured 200 resources — a lower bound on what it actually fetched — so the first
    attempt is charged 200, and the second would breach. A loop that charged only the
    declared cost launches twice here.
    """
    client = FakeLoopClient(
        outcomes=[_failing_outcome(captured=200)],
    )
    journal = _drive(
        client,
        _budget(max_attempts=5, declared_requests_per_attempt=100, max_upstream_requests=250),
    )

    assert len(client.launches) == 1
    assert journal["stop_reason"] == STOP_REQUEST_CEILING_REACHED
    assert journal["spend"]["upstream_requests_authorised"] == 200
    assert journal["spend"]["reconciled_overruns"] == [
        {"attempt": 1, "observed_floor": 200, "extra_charged": 100}
    ]


def test_a_cheap_attempt_is_never_refunded() -> None:
    """A run that captured less than declared must not buy back ceiling."""
    client = FakeLoopClient(outcomes=[_failing_outcome(captured=1)])
    journal = _drive(
        client,
        _budget(max_attempts=2, declared_requests_per_attempt=100, max_upstream_requests=1000),
    )
    assert journal["spend"]["upstream_requests_authorised"] == 200
    assert journal["spend"]["reconciled_overruns"] == []


def test_observed_request_floor_is_a_floor_not_a_count() -> None:
    assert observed_request_floor(_run(captured=12, artifacts=40)) == 40
    assert observed_request_floor(_run(captured=0, artifacts=0)) == 0
    assert observed_request_floor({}) == 0


def test_a_budget_cannot_be_unlimited() -> None:
    """There is no sentinel for 'no limit', and a falsy bound is rejected, not inherited."""
    for kwargs in (
        {"max_attempts": 0},
        {"max_attempts": -1},
        {"max_upstream_requests": 0},
        {"declared_requests_per_attempt": 0},
    ):
        with pytest.raises(BudgetError):
            _budget(**kwargs)


def test_a_budget_whose_attempt_cannot_fit_is_rejected_rather_than_stalling() -> None:
    with pytest.raises(BudgetError):
        _budget(declared_requests_per_attempt=500, max_upstream_requests=100)


# ---------------------------------------------------------------------------------
# Bound 3 — a refusal is terminal
# ---------------------------------------------------------------------------------


def test_a_refusal_is_terminal_with_attempts_and_ceiling_still_unspent() -> None:
    """The guard, in the fixture where an unbounded loop would differ.

    Five attempts and a 100,000 ceiling are available and the refusal is the ONLY thing
    stopping the loop. A loop that treated a refusal as a failure to retry would launch
    five runs against a portal a human closed — and platform-control would see five
    ordinary requests.
    """
    refused = _run("run_ref", status="failed", refused=True, refusal_code="provider_not_live_ready")
    client = FakeLoopClient(outcomes=[{"launch": refused, "polls": [(refused, _health())]}])
    journal = _drive(client, _budget(max_attempts=5, max_upstream_requests=100_000))

    assert len(client.launches) == 1
    assert journal["stop_reason"] == STOP_REFUSED
    assert journal["spend"]["attempts_remaining"] == 4
    assert journal["spend"]["upstream_requests_remaining"] > 0
    assert journal["refusals"] == [{"code": "provider_not_live_ready", "detail": ""}]
    assert client.sleeps == []  # it did not even back off to try again


def test_a_refusal_on_a_later_attempt_is_just_as_terminal() -> None:
    """The refusal check must not be a first-attempt special case.

    Attempt 1 fails retryably, attempt 2 is refused. Three attempts were authorised, so a
    loop that only honoured refusals before the first launch would take the third.
    """
    refused = _run("run_2", status="failed", refused=True, refusal_code="compliance_policy_missing")
    client = FakeLoopClient(
        outcomes=[
            _failing_outcome("run_1"),
            {"launch": refused, "polls": [(refused, _health())]},
        ]
    )
    journal = _drive(client, _budget(max_attempts=3, max_upstream_requests=100_000))

    assert len(client.launches) == 2
    assert journal["stop_reason"] == STOP_REFUSED
    assert journal["spend"]["attempts_remaining"] == 1


def test_a_refusal_returned_by_the_launch_call_itself_is_terminal_before_any_poll() -> None:
    """The launch-time refusal check is load-bearing on its own, not a duplicate.

    A dispatch refused at `POST /v1/runs` — in particular a 409, which
    `acquisition_loop_cmd` translates into this shape — carries no `run_id`, so there is
    nothing to poll. The fake refuses to be polled here, so a loop that leaned on the
    poll-time refusal check instead fails rather than quietly working.
    """
    refused = {
        "refused": True,
        "refusal_code": "blueprint_template_not_enabled",
        "failure_reason": "template ch/lexfind_zh_hundegesetz is not enabled",
        "status": "failed",
    }
    client = FakeLoopClient(outcomes=[{"launch": refused, "polls": []}])
    journal = _drive(client, _budget(max_attempts=4, max_upstream_requests=100_000))

    assert client.polls == []
    assert journal["stop_reason"] == STOP_REFUSED
    assert journal["refusals"][0]["code"] == "blueprint_template_not_enabled"
    assert journal["spend"]["attempts_remaining"] == 3


def test_a_refusal_discovered_while_polling_is_terminal() -> None:
    """A dispatch accepted then refused must not be read as a retryable failure."""
    client = FakeLoopClient(
        outcomes=[
            {
                "launch": _run("run_p", status="pending", captured=0),
                "polls": [
                    (
                        _run("run_p", status="failed", refused=True, refusal_code=None),
                        _health(),
                    )
                ],
            }
        ]
    )
    journal = _drive(client, _budget(max_attempts=4, max_upstream_requests=100_000))
    assert len(client.launches) == 1
    assert journal["stop_reason"] == STOP_REFUSED
    # An absent code means "not classified", never "not refused" (#908).
    assert journal["refusals"][0]["code"] == "refused_without_code"


def test_a_preflight_refusal_launches_nothing_at_all() -> None:
    client = FakeLoopClient(readiness_payload=REFUSED_PREFLIGHT, outcomes=[_failing_outcome()])
    journal = _drive(client, _budget(max_attempts=5, max_upstream_requests=100_000))

    assert client.launches == []
    assert journal["stop_reason"] == STOP_REFUSED
    assert journal["spend"]["upstream_requests_authorised"] == 0
    assert journal["refusals"][0]["code"] == "acquisition_lock_open"


def test_an_unreadable_readiness_payload_is_not_readiness() -> None:
    """Fails closed: a payload that says nothing must not read as permission."""
    assert readiness_refusals({})[0]["code"] == "readiness_unreadable"
    assert readiness_refusals({"ready": True, "checks": []}) == []
    assert readiness_refusals({"ready": False, "checks": []})[0]["code"] == "readiness_unreadable"


def test_no_refusal_code_is_ever_retryable() -> None:
    """The retryable set is one cause, and it is not the refusal one."""
    assert STALL_RUN_REFUSED not in AGENT_RETRYABLE_CAUSES
    assert AGENT_RETRYABLE_CAUSES == {"run_failed"}


# ---------------------------------------------------------------------------------
# What the loop refuses to answer with another run
# ---------------------------------------------------------------------------------


def test_an_environment_defect_is_reported_rather_than_re_run() -> None:
    """`publish_path_disabled` is a config defect; a second run adds load and no information."""
    # Zero captures, so the run does NOT earn evidence on its own terms — otherwise this
    # fixture would stop at `acceptance_evidence_captured` and assert nothing about the
    # diagnosis path.
    completed = _run("run_np", status="completed", captured=0)
    client = FakeLoopClient(
        outcomes=[
            {
                "launch": _run("run_np", status="pending", captured=0),
                "polls": [
                    (
                        completed,
                        _health(
                            processing_events=0,
                            lifecycle_events=0,
                            stages=[
                                {"stage": "acquisition", "status": "ok"},
                                {"stage": "document_intelligence", "status": "pending"},
                                {"stage": "projection", "status": "pending"},
                                {"stage": "search", "status": "pending"},
                            ],
                        ),
                    )
                ],
            }
        ]
    )
    # The run completes and is not refused, so only the diagnosis stops the loop here.
    journal = _drive(client, _budget(max_attempts=4, max_upstream_requests=100_000))

    assert len(client.launches) == 1
    assert journal["stop_reason"] == STOP_NEEDS_HUMAN
    assert journal["diagnosis"]["cause"] == "publish_path_disabled"


def test_a_run_the_loop_can_no_longer_observe_is_cancelled_not_abandoned() -> None:
    """Stopping is part of the loop's duty: unobserved load is unaccounted load."""
    pending = _run("run_stuck", status="pending", captured=0)
    client = FakeLoopClient(outcomes=[{"launch": pending, "polls": [(pending, _health())]}])
    journal = _drive(client, _budget(max_attempts=3, max_polls_per_attempt=3))

    assert client.cancels == ["run_stuck"]
    assert journal["stop_reason"] == STOP_POLL_BUDGET_EXHAUSTED
    assert len(client.launches) == 1


# ---------------------------------------------------------------------------------
# Attribution and the boundary this loop must not cross
# ---------------------------------------------------------------------------------


def test_every_call_is_attributed_to_an_agent_and_never_to_a_person() -> None:
    client = FakeLoopClient(
        outcomes=[
            {
                "launch": _run("run_ok", status="pending", captured=0),
                "polls": [(_run("run_ok", captured=3), _health())],
            }
        ]
    )
    journal = _drive(client, _budget())

    assert journal["actor"] == "agent"
    assert journal["correlation_id"].startswith(f"{CORRELATION_PREFIX}:")
    assert client.launches[0]["correlation_id"] == journal["correlation_id"]
    assert journal["attempts"][0]["actor"] == "agent"

    # ADR-0038 "a non-person must not appear as one": there is no parameter through
    # which a caller could attribute this loop to a human.
    params = set(inspect.signature(drive_acquisition).parameters)
    assert not params & {"operator", "operator_id", "user", "user_id", "reviewed_by", "person"}
    assert "actor" not in inspect.signature(agent_attribution).parameters


def test_a_supplied_correlation_id_is_still_marked_as_an_agent() -> None:
    assert agent_attribution(correlation_id="zh-backfill")["correlation_id"] == (
        "agent:zh-backfill"
    )
    assert agent_attribution(correlation_id="agent:zh")["correlation_id"] == "agent:zh"


def test_the_loop_never_reaches_for_the_enablement_key() -> None:
    """ADR-0030's second key is a human's (#854), and this loop does not approach it.

    The server refuses the flip anyway — but an agent that had to be refused has already
    tried, and the decision is made here.
    """
    source = _code_without_prose(acquisition_loop)
    assert "/enablement" not in source
    # Prose may name the key — it must, to explain the boundary — but nothing the module
    # *calls* may. `_STOP_DETAIL` says "flipping `enabled: true` is a human's key", which
    # a naive substring scan cannot tell from a call that flips it.
    called = _called_names(acquisition_loop)
    assert not [name for name in called if "enabl" in name.lower()]
    assert {m for m in dir(LoopClient) if not m.startswith("_")} == {
        "readiness",
        "launch",
        "poll",
        "cancel",
        "sleep",
    }


def test_the_loop_never_authors_a_source_version() -> None:
    """Adjusting the spec is out of the loop's reach, not merely unused.

    A new spec is what a request budget cannot bound: the declared per-attempt cost the
    ceiling charges against was stated for the old one.
    """
    source = _code_without_prose(acquisition_loop)
    assert "/versions" not in source
    assert not [m for m in dir(LoopClient) if "version" in m and not m.startswith("_")]
    assert not [n for n in _called_names(acquisition_loop) if "version" in n.lower()]


def test_the_decision_module_stays_free_of_http_and_clocks() -> None:
    """The same rule coverage.py and agent_loop.py follow — branching testable without a stack."""
    source = _code_without_prose(acquisition_loop)
    assert "httpx" not in source
    assert "request_json" not in source
    assert "time.sleep" not in source


def test_only_acceptance_runs_are_ever_launched() -> None:
    client = FakeLoopClient(outcomes=[_failing_outcome()])
    _drive(client, _budget(max_attempts=2, max_upstream_requests=100_000))
    assert {launch["mode"] for launch in client.launches} == {"acceptance"}
