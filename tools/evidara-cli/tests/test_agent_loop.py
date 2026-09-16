"""The operator agent's decision layer, and the boundary it must not cross (#909).

Two of these tests are the point of the module. `test_no_refusal_is_ever_agent_
actionable` and `test_the_agent_never_reaches_for_the_enablement_key` are the guards;
the rest exist so those two cannot be satisfied by a planner that refuses everything.

Why the boundary needs a client-side guard at all, when #854 already moved the
ADR-0030 two-key check server-side: the server can refuse a key flip, but it cannot
tell a legitimate retry from an agent grinding at a refusal until it succeeds. Both
arrive as ordinary requests. "A refusal is an outcome, not an obstacle" is therefore
enforced where the decision is made.
"""

from __future__ import annotations

import inspect

import pytest

from evidara_cli import agent_loop
from evidara_cli.agent_loop import (
    AGENT_ACTIONABLE,
    HUMAN_ONLY,
    AgentAction,
    action_for,
    actor_for,
    plan_from_queue,
    summarize_plan,
    unplannable_items,
)


def _queue(*items: dict) -> dict:
    return {
        "basis": "platform_control_runs",
        "ordering": "reason_class_then_name",
        "unqueued_unmeasurable": 0,
        "data": list(items),
        "total": len(items),
        "limit": 50,
    }


def _item(jurisdiction_id: str, reasons: list[str], **overrides) -> dict:
    return {
        "jurisdiction_id": jurisdiction_id,
        "name": jurisdiction_id.upper(),
        "slug": jurisdiction_id,
        "level": "cantonal",
        "reasons": reasons,
        "expected": None,
        "denominator_tier": "none",
        "acquired_distinct_urls": 0,
        "processed_documents": 0,
        "acquired_gap": None,
        "processed_gap": None,
        "refused_runs": 0,
        "quarantined_documents": 0,
        "source_ids": [],
        **overrides,
    }


# ---------------------------------------------------------------------------
# The guards
# ---------------------------------------------------------------------------


def test_no_refusal_is_ever_agent_actionable() -> None:
    """A refused run is a decision someone made, not a transient failure.

    A closed config key is how an operator stops traffic at one portal when an
    authority complains about load. An agent that retried it would be overriding a
    human by persistence rather than by permission — and every request it sent would
    look normal to the server, so no server-side check would notice.
    """
    assert AgentAction.RESOLVE_REFUSAL in HUMAN_ONLY
    assert AgentAction.RESOLVE_REFUSAL not in AGENT_ACTIONABLE

    plan = plan_from_queue(_queue(_item("jur_zh", ["refusals_outstanding"], refused_runs=2)))
    assert [w.actor for w in plan] == ["human"]

    summary = summarize_plan(_queue(_item("jur_zh", ["refusals_outstanding"], refused_runs=2)))
    assert summary["agent_actionable"] == []
    assert len(summary["human_only"]) == 1


def test_the_agent_never_reaches_for_the_enablement_key() -> None:
    """`enabled: true` requires bound evidence plus a human acknowledgement (#854).

    The server refuses otherwise — but an agent that had to be refused would already
    have tried, and this module is where that decision is made. Note the same CLI
    *does* ship `coverage enable`: that is an operator command, and no action this
    planner emits maps to it.
    """
    source = inspect.getsource(agent_loop)
    # The module may NAME the forbidden endpoint (it does, as a constant this test
    # reads) but must never build a call to it.
    assert "request_json" not in source
    assert "httpx" not in source
    for action in AgentAction:
        assert "enable" not in action.value


def test_refusals_outrank_acquisition_so_a_refused_jurisdiction_is_never_re_run() -> None:
    """The ordering matters, not just the classification.

    A refused jurisdiction usually also reports `never_acquired` — nothing was
    captured, because the run was refused. If `never_acquired` won, the agent would
    plan an acceptance run against exactly the source a human closed.
    """
    plan = plan_from_queue(
        _queue(
            _item(
                "jur_zh",
                ["never_acquired", "acquisition_gap", "refusals_outstanding"],
                refused_runs=1,
            )
        )
    )
    assert plan[0].action is AgentAction.RESOLVE_REFUSAL
    assert plan[0].actor == "human"


# ---------------------------------------------------------------------------
# ...and the tests that stop those being satisfied by refusing everything
# ---------------------------------------------------------------------------


@pytest.mark.parametrize(
    ("reasons", "action"),
    [
        (["no_denominator"], AgentAction.ENUMERATE_DENOMINATOR),
        (["never_acquired"], AgentAction.RUN_ACCEPTANCE),
        (["acquisition_gap"], AgentAction.RUN_ACCEPTANCE),
        (["processing_gap"], AgentAction.AWAIT_PIPELINE),
    ],
)
def test_the_agent_does_act_where_it_may(reasons: list[str], action: AgentAction) -> None:
    plan = plan_from_queue(_queue(_item("jur_zh", reasons)))
    assert plan[0].action is action
    assert plan[0].actor == "agent"


def test_holding_more_than_the_denominator_is_a_finding_not_a_run() -> None:
    """There is no acquisition run that fixes holding more than the source publishes.

    It is a dedup failure or a denominator counting something else. Planning a run
    would add captures to the very number that is already too high.
    """
    plan = plan_from_queue(_queue(_item("jur_zh", ["holdings_exceed_denominator"])))
    assert plan[0].action is AgentAction.INVESTIGATE_HOLDINGS
    assert plan[0].actor == "human"


def test_a_backlog_is_waited_on_rather_than_re_acquired() -> None:
    """`processing_gap` means captured-not-processed. Running acquisition again would
    lengthen the queue it is waiting on."""
    plan = plan_from_queue(_queue(_item("jur_zh", ["processing_gap"])))
    assert plan[0].action is AgentAction.AWAIT_PIPELINE


# ---------------------------------------------------------------------------
# Honesty about what the plan does not cover
# ---------------------------------------------------------------------------


def test_a_reason_this_client_does_not_know_is_reported_not_dropped() -> None:
    """ "There is no work" and "there is work I do not understand" are different answers.

    The server may add a reason before this client learns it. Silently skipping it
    would make the plan quietly incomplete — the same collapse between zero and
    unknown the ledger refuses.
    """
    payload = _queue(_item("jur_zh", ["some_reason_shipped_later"]))
    assert plan_from_queue(payload) == []
    assert len(unplannable_items(payload)) == 1

    summary = summarize_plan(payload)
    assert summary["complete"] is False
    assert len(summary["unplannable"]) == 1


def test_a_plan_is_incomplete_while_the_server_could_not_speak_about_every_jurisdiction() -> None:
    payload = _queue(_item("jur_zh", ["no_denominator"]))
    payload["unqueued_unmeasurable"] = 3
    assert summarize_plan(payload)["complete"] is False


def test_a_clean_full_queue_reports_complete() -> None:
    """Without this, `complete` could be hard-wired to False and every test above
    would still pass."""
    summary = summarize_plan(_queue(_item("jur_zh", ["no_denominator"])))
    assert summary["complete"] is True


def test_the_plan_echoes_the_servers_ordering_instead_of_inventing_one() -> None:
    """A second ranking in the client is how one rule ends up enforced twice with the
    weaker copy winning. The server states its rule; this repeats it verbatim."""
    summary = summarize_plan(_queue(_item("jur_zh", ["no_denominator"])))
    assert summary["ordering"] == "reason_class_then_name"
    for item in summary["agent_actionable"] + summary["human_only"]:
        assert "score" not in item
        assert "priority" not in item


def test_an_unclassified_action_raises_rather_than_defaulting() -> None:
    """A default of "agent" would silently grant autonomy to anything added later; a
    default of "human" would hide a mapping mistake behind a stall."""

    class _Rogue(str):
        pass

    with pytest.raises(ValueError, match="classify it deliberately"):
        actor_for(_Rogue("something_new"))  # type: ignore[arg-type]


def test_every_action_is_classified() -> None:
    """The two sets must together cover the enum — otherwise `actor_for` raises at
    runtime for a value the module itself defines."""
    assert AGENT_ACTIONABLE | HUMAN_ONLY == set(AgentAction)
    assert not (AGENT_ACTIONABLE & HUMAN_ONLY)


def test_action_for_returns_none_rather_than_guessing() -> None:
    assert action_for([]) is None


def test_a_sourceless_jurisdiction_is_a_human_action_not_an_agent_one() -> None:
    """Registering a source is a repo edit and a deploy (#736).

    The server reports these as a count rather than as rows (#928), so this should
    not normally arrive — but the value is in the published contract enum, and a
    client that cannot classify a value the contract can produce is fragile. This
    pins that if it does arrive it is classified deliberately, and to the right side
    of the autonomy boundary.
    """
    plan = plan_from_queue(_queue(_item("jur_bare", ["no_source"])))
    assert plan[0].action is AgentAction.REGISTER_SOURCE
    assert plan[0].actor == "human"


class TestServerOwnsTheMapping:
    """#964: the reason -> action mapping belongs to the server, not to each client.

    It lived only here, in Python, so the operator panel would have needed a third
    copy (ADR-0056 constraint 1). Two already disagreed: read off the queue's own
    sort order, `refusals_outstanding` + `never_acquired` — the NORMAL shape of a
    refusal, every run refused so nothing acquired — resolved to `run_acceptance`,
    an agent retrying work a person had refused.
    """

    def _item(self, **overrides):
        item = {
            "jurisdiction_id": "jur_ch_zh",
            "name": "Zürich",
            "reasons": ["refusals_outstanding", "never_acquired"],
            "source_ids": ["src_x"],
            "expected": 120,
            "acquired_distinct_urls": 0,
            "refused_runs": 3,
        }
        item.update(overrides)
        return {"data": [item], "ordering": "reason_class_then_name"}

    def test_the_servers_action_wins_over_the_local_mapping(self):
        # The server says await_pipeline; the local mapping would say resolve_refusal.
        # Delete the `_server_action` call in `plan_from_queue` and this goes red.
        payload = self._item(proposed_action="await_pipeline", actor="agent")
        plan = agent_loop.plan_from_queue(payload)
        assert [p.action for p in plan] == [agent_loop.AgentAction.AWAIT_PIPELINE]

    def test_the_servers_actor_wins_over_the_local_classification(self):
        # Local classification of resolve_refusal is "human". The server saying
        # "human" for an action the client would call agent-actionable must also hold.
        payload = self._item(proposed_action="run_acceptance", actor="human")
        plan = agent_loop.plan_from_queue(payload)
        assert [p.actor for p in plan] == ["human"]

    def test_an_unknown_actor_is_never_read_as_permission(self):
        # This is the autonomy boundary. An unrecognised string must fall through to
        # the local classification, never be trusted, and never mean "agent".
        payload = self._item(proposed_action="resolve_refusal", actor="supervisor")
        plan = agent_loop.plan_from_queue(payload)
        assert [p.actor for p in plan] == ["human"]

    def test_an_unknown_action_falls_back_rather_than_crashing(self):
        payload = self._item(proposed_action="teleport", actor=None)
        plan = agent_loop.plan_from_queue(payload)
        assert [p.action for p in plan] == [agent_loop.AgentAction.RESOLVE_REFUSAL]

    def test_a_server_without_the_field_still_plans(self):
        # Backwards compatible: an older server states neither field.
        plan = agent_loop.plan_from_queue(self._item())
        assert [p.action for p in plan] == [agent_loop.AgentAction.RESOLVE_REFUSAL]
        assert [p.actor for p in plan] == ["human"]

    def test_the_964_case_is_human_under_the_local_fallback_too(self):
        """The fallback must not be the unsafe ordering.

        If someone ever reorders `_REASON_TO_ACTION` so a gap outranks a refusal,
        this fails — which is the whole defect, reproduced at its smallest.
        """
        action = agent_loop.action_for(["never_acquired", "refusals_outstanding"])
        assert agent_loop.actor_for(action) == "human"


class TestRegisterSourceSplitMirrorsTheServer:
    """The CLI mirrors the server's vocabulary; #964 is what happens when it drifts.

    `register_source` was one action doing two jobs. With no blueprint template it
    needs a repo edit and a deploy (#736) and stays human. With one, creating a
    source is an API call against a blueprint an author already wrote.
    """

    def test_the_template_variant_is_agent_actionable(self) -> None:
        assert AgentAction.REGISTER_SOURCE_FROM_TEMPLATE in AGENT_ACTIONABLE
        assert actor_for(AgentAction.REGISTER_SOURCE_FROM_TEMPLATE) == "agent"

    def test_the_deploy_variant_stays_human(self) -> None:
        assert AgentAction.REGISTER_SOURCE in HUMAN_ONLY
        assert actor_for(AgentAction.REGISTER_SOURCE) == "human"

    def test_the_server_reason_maps_without_falling_through_to_unplannable(self) -> None:
        """An action the server names and this client has not learned lands in
        `unplannable_items`, so the mapping is what makes the split usable at all."""
        payload = {
            "data": [{"jurisdiction_id": "jur_ch_be", "reasons": ["no_source_template_available"]}]
        }
        assert unplannable_items(payload) == []
        plan = plan_from_queue(payload)
        assert len(plan) == 1
        assert plan[0].action is AgentAction.REGISTER_SOURCE_FROM_TEMPLATE
        assert plan[0].actor == "agent"

    def test_a_sourceless_jurisdiction_with_no_template_is_still_human(self) -> None:
        plan = plan_from_queue(
            {"data": [{"jurisdiction_id": "jur_ch_gemeinde_1", "reasons": ["no_source"]}]}
        )
        assert plan[0].action is AgentAction.REGISTER_SOURCE
        assert plan[0].actor == "human"

    def test_every_action_is_classified(self) -> None:
        """`actor_for` is total and raises for an unclassified action, so a member
        added without a deliberate classification fails loudly rather than
        inheriting autonomy."""
        for action in AgentAction:
            assert actor_for(action) in {"agent", "human"}
