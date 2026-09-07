"""The operator agent's decision layer: what to work on next, and who may do it.

#909, and the first thing that could not be built before #907/#921 existed. Every
*step* of the coverage loop was already a command here — `coverage templates`,
`preflight`, `watch`, `enable` — and nothing read a denominator to decide which
jurisdiction to spend a run on. An agent without that onboards enthusiastically and
nobody can say afterwards whether coverage improved.

`GET /v1/acquisition-coverage/queue` is that denominator, turned into a worklist. This
module is the pure function over its payload: no HTTP, no side effects, so the
branching an agent depends on is unit-testable without a stack — the same rule
`coverage.py` already follows.

## The autonomy boundary is not invented here

#854 moved the ADR-0030 two-key guard **server-side**: flipping `enabled: true`
requires bound acceptance evidence plus a human acknowledgement, and the server
refuses otherwise with a machine-readable code. That boundary is enforced where it
cannot be bypassed, and this module does not restate it — it stays on the correct side
of it.

What this module *does* add is the second half of the same idea, which the server
cannot enforce: **a refusal is an outcome the agent reports, never an obstacle it works
around.** A refused run is a decision someone made — a closed config key is how an
operator stops traffic at a portal when an authority complains about load. An agent
that retried it would be overriding a human by persistence rather than by permission,
and no server-side check would see anything but a normal request.

So actions are split by ACTOR, not only by kind, and
`test_no_refusal_is_ever_agent_actionable` fails if that ever stops being true.
"""

from __future__ import annotations

from dataclasses import dataclass, field
from enum import StrEnum
from typing import Any


class AgentAction(StrEnum):
    """What the loop proposes for one jurisdiction."""

    ENUMERATE_DENOMINATOR = "enumerate_denominator"
    """Nothing has told us how much this jurisdiction publishes. Run an enumeration
    first: every other answer about it is unstatable until this exists, which is why
    the queue sorts `no_denominator` ahead of everything else."""

    RUN_ACCEPTANCE = "run_acceptance"
    """A denominator exists and we hold less than it. An acceptance run is the
    evidence primitive (ADR-0030) and the agent may run one itself."""

    AWAIT_PIPELINE = "await_pipeline"
    """Captured, not yet processed. The action is to wait and re-check — NOT to run
    acquisition again, which would add captures to a backlog rather than clear it."""

    INVESTIGATE_HOLDINGS = "investigate_holdings"
    """We hold MORE than the source claims to publish. Not progress: a dedup failure,
    or a denominator counting something else. There is no run that fixes it."""

    RESOLVE_REFUSAL = "resolve_refusal"
    """A run here was refused. The refusal is the answer, and a person decides what
    happens next."""

    REGISTER_SOURCE = "register_source"
    """There is no source for this jurisdiction, so there is nothing to act through.
    Registering one is a repo edit and a deploy (#736), which no action here can do.

    The server does not normally emit `no_source` in the queue's `data` — it reports
    those as a count instead (#928) — but the value is in the published contract enum,
    and a client that cannot classify a value the contract can produce is fragile.
    Mapped so that if it ever arrives it is classified deliberately rather than
    landing in `unplannable` as though this client were out of date."""


#: Actions the agent may carry out on its own.
AGENT_ACTIONABLE: frozenset[AgentAction] = frozenset(
    {
        AgentAction.ENUMERATE_DENOMINATOR,
        AgentAction.RUN_ACCEPTANCE,
        AgentAction.AWAIT_PIPELINE,
    }
)

#: Actions that belong to a person. Not a UI convention — the boundary this module
#: exists to hold. Both are cases where *doing something* is the wrong response:
#: a refusal is a decision to respect, and holdings exceeding a denominator is a
#: measurement problem no run can resolve.
HUMAN_ONLY: frozenset[AgentAction] = frozenset(
    {
        AgentAction.RESOLVE_REFUSAL,
        AgentAction.INVESTIGATE_HOLDINGS,
        AgentAction.REGISTER_SOURCE,
    }
)

#: The one server call the agent must never make. Named so
#: `test_the_agent_never_reaches_for_the_enablement_key` can assert its absence from
#: this module's own source; the server refuses it anyway (#854), and an agent that
#: had to be refused would already have tried.
FORBIDDEN_ENDPOINT = "/enablement"

# Queue reason -> action. One place, so the mapping is reviewable rather than spread
# through branches. Ordered most-blocking first, mirroring the server's own
# `_WORK_REASON_ORDER`; the first reason that matches decides the action.
_REASON_TO_ACTION: tuple[tuple[str, AgentAction], ...] = (
    ("no_source", AgentAction.REGISTER_SOURCE),
    ("no_denominator", AgentAction.ENUMERATE_DENOMINATOR),
    ("refusals_outstanding", AgentAction.RESOLVE_REFUSAL),
    ("holdings_exceed_denominator", AgentAction.INVESTIGATE_HOLDINGS),
    ("never_acquired", AgentAction.RUN_ACCEPTANCE),
    ("acquisition_gap", AgentAction.RUN_ACCEPTANCE),
    ("processing_gap", AgentAction.AWAIT_PIPELINE),
)


@dataclass(frozen=True)
class PlannedWork:
    """One jurisdiction, one proposed action, and who may take it."""

    jurisdiction_id: str
    name: str
    action: AgentAction
    actor: str
    """`"agent"` or `"human"`. Derived from the action, never passed in."""
    reasons: list[str] = field(default_factory=list)
    source_ids: list[str] = field(default_factory=list)
    expected: int | None = None
    acquired_distinct_urls: int = 0
    refused_runs: int = 0

    def as_dict(self) -> dict[str, Any]:
        return {
            "jurisdiction_id": self.jurisdiction_id,
            "name": self.name,
            "action": self.action.value,
            "actor": self.actor,
            "reasons": list(self.reasons),
            "source_ids": list(self.source_ids),
            # Same nullability contract as the ledger: None is "unknown", never zero.
            "expected": self.expected,
            "acquired_distinct_urls": self.acquired_distinct_urls,
            "refused_runs": self.refused_runs,
        }


def action_for(reasons: list[str]) -> AgentAction | None:
    """The single action for one queue item's reasons, or None if none apply.

    A jurisdiction usually carries several reasons at once — `no_denominator` and
    `never_acquired` are both true of an untouched one. The most blocking wins, and
    the full reason list travels on the plan so nothing is hidden by the choice.
    """
    for reason, action in _REASON_TO_ACTION:
        if reason in reasons:
            return action
    return None


def actor_for(action: AgentAction) -> str:
    """Who may take this action.

    Deliberately total: an action in neither set raises rather than defaulting. A
    default of `"agent"` would silently grant autonomy to anything added later, and a
    default of `"human"` would hide a mapping mistake behind a stall.
    """
    if action in AGENT_ACTIONABLE:
        return "agent"
    if action in HUMAN_ONLY:
        return "human"
    raise ValueError(
        f"{action} is in neither AGENT_ACTIONABLE nor HUMAN_ONLY — classify it "
        "deliberately rather than letting it inherit a default"
    )


def plan_from_queue(payload: dict[str, Any]) -> list[PlannedWork]:
    """Turn `GET /v1/acquisition-coverage/queue` into a plan, in the server's order.

    The order is NOT re-derived here. The server states its ordering rule in the
    payload (`ordering`) precisely so a consumer does not invent a competing one, and
    a second ranking in the client is how the same rule ends up enforced twice with
    the weaker copy winning (AGENTS.md).
    """
    items = payload.get("data") or []
    plan: list[PlannedWork] = []
    for item in items:
        if not isinstance(item, dict):
            continue
        reasons = [r for r in (item.get("reasons") or []) if isinstance(r, str)]
        action = action_for(reasons)
        if action is None:
            # A reason the server added and this client does not know. Skipping it
            # silently would make the plan quietly incomplete, so it is surfaced by
            # `unplannable_items` rather than dropped here.
            continue
        plan.append(
            PlannedWork(
                jurisdiction_id=str(item.get("jurisdiction_id", "")),
                name=str(item.get("name", "")),
                action=action,
                actor=actor_for(action),
                reasons=reasons,
                source_ids=[s for s in (item.get("source_ids") or []) if isinstance(s, str)],
                expected=item.get("expected"),
                acquired_distinct_urls=int(item.get("acquired_distinct_urls") or 0),
                refused_runs=int(item.get("refused_runs") or 0),
            )
        )
    return plan


def unplannable_items(payload: dict[str, Any]) -> list[dict[str, Any]]:
    """Queue items this client could not map to an action.

    The server may add a reason before this client learns it. Reporting those is the
    difference between "there is no work" and "there is work I do not understand" —
    the same distinction the ledger draws between a zero and an unknown, and the
    reason `summarize_plan` refuses to call a plan complete while any exist.
    """
    unplannable: list[dict[str, Any]] = []
    for item in payload.get("data") or []:
        if not isinstance(item, dict):
            continue
        reasons = [r for r in (item.get("reasons") or []) if isinstance(r, str)]
        if action_for(reasons) is None:
            unplannable.append(item)
    return unplannable


def summarize_plan(payload: dict[str, Any]) -> dict[str, Any]:
    """The whole loop's answer: what the agent will do, what it will not, and why."""
    plan = plan_from_queue(payload)
    unplannable = unplannable_items(payload)
    return {
        # Echoed, not restated: a consumer must be able to tell that this plan is a
        # view of the server's order rather than a second opinion about priority.
        "ordering": payload.get("ordering"),
        "queue_total": payload.get("total"),
        "unqueued_unmeasurable": payload.get("unqueued_unmeasurable", 0),
        "agent_actionable": [w.as_dict() for w in plan if w.actor == "agent"],
        "human_only": [w.as_dict() for w in plan if w.actor == "human"],
        "unplannable": unplannable,
        # A plan is only complete if nothing was skipped and the server could speak
        # about every jurisdiction. Anything else is reported, never rounded away.
        "complete": not unplannable and not payload.get("unqueued_unmeasurable"),
    }
