"""The honesty rules of the acquisition-coverage read model, one test each.

These are the rules that decide whether the ledger is worth having. A ledger that reports
"100%" against an unknown denominator is worse than no ledger — it manufactures exactly
the false green this repo keeps getting caught by (#685, #735, #744, #772). So each rule
below is a validator, and each validator is asserted in both directions: the honest shape
is accepted, and the dishonest one is refused.
"""

from __future__ import annotations

import pytest
from pydantic import ValidationError

from platform_control.domain import (
    HUMAN_ONLY_ACTIONS,
    REASON_ACTION_PRIORITY,
    CoverageWorkAction,
    CoverageWorkActor,
    CoverageWorkReason,
    DenominatorTier,
    NormLevel,
    resolve_work_action,
    resolve_work_actor,
)
from platform_control.schemas.coverage import AcquisitionCoverageEntry


def _entry(**overrides) -> dict:
    base = {
        "jurisdiction_id": "jur_ch_zh",
        "name": "Kanton Zürich",
        "slug": "ch-zh",
        "level": NormLevel.CANTONAL,
        "expected": 1377,
        "denominator_tier": DenominatorTier.PUBLISHED,
        "acquired_distinct_urls": 1377,
        "processed_documents": 1374,
        "acquired_gap": 0,
        "processed_gap": 3,
    }
    base.update(overrides)
    return base


def test_a_complete_measurement_is_accepted() -> None:
    entry = AcquisitionCoverageEntry(**_entry())
    assert entry.acquired_gap == 0
    assert entry.processed_gap == 3


def test_unknown_denominator_is_null_never_zero() -> None:
    """No denominator means no gap — not a gap of zero.

    `expected: 0` alongside `observed: 0` is how a ledger says "this canton publishes no
    law and we hold all of it". The tier and the gaps must all collapse together.
    """
    entry = AcquisitionCoverageEntry(
        **_entry(
            expected=None,
            denominator_tier=DenominatorTier.NONE,
            acquired_gap=None,
            processed_gap=None,
        )
    )
    assert entry.expected is None
    assert entry.acquired_gap is None

    with pytest.raises(ValidationError, match="gap without a denominator"):
        AcquisitionCoverageEntry(
            **_entry(expected=None, denominator_tier=DenominatorTier.NONE, acquired_gap=0)
        )


def test_a_tier_may_not_promise_a_denominator_it_does_not_carry() -> None:
    with pytest.raises(ValidationError, match="denominator_tier must be 'none'"):
        AcquisitionCoverageEntry(
            **_entry(
                expected=None,
                denominator_tier=DenominatorTier.PUBLISHED,
                acquired_gap=None,
                processed_gap=None,
            )
        )
    with pytest.raises(ValidationError, match="cannot carry an expected count"):
        AcquisitionCoverageEntry(**_entry(expected=1377, denominator_tier=DenominatorTier.NONE))


def test_registry_tier_never_emits_a_gap() -> None:
    """2110 communes minus 3 documents is a number in no unit at all.

    A registry denominator counts UNITS; the numerators count documents. The subtraction
    is a category error that would render as a coverage gap, so it is refused outright —
    breadth is claimable, depth is not.
    """
    entry = AcquisitionCoverageEntry(
        **_entry(
            jurisdiction_id="jur_ch",
            expected=2110,
            denominator_tier=DenominatorTier.REGISTRY,
            acquired_distinct_urls=3,
            acquired_gap=None,
            processed_gap=None,
        )
    )
    assert entry.expected == 2110
    assert entry.acquired_gap is None

    with pytest.raises(ValidationError, match="counts units, not documents"):
        AcquisitionCoverageEntry(
            **_entry(expected=2110, denominator_tier=DenominatorTier.REGISTRY, acquired_gap=2107)
        )


def test_truncated_run_is_a_sample_not_a_measurement() -> None:
    entry = AcquisitionCoverageEntry(
        **_entry(denominator_truncated=True, acquired_gap=None, processed_gap=None)
    )
    assert entry.denominator_truncated is True

    with pytest.raises(ValidationError, match="sample, not a measurement"):
        AcquisitionCoverageEntry(**_entry(denominator_truncated=True, acquired_gap=1277))


def test_truncated_run_cannot_claim_completeness() -> None:
    with pytest.raises(ValidationError, match="cannot claim completeness"):
        AcquisitionCoverageEntry(
            **_entry(
                denominator_truncated=True,
                provider_complete_claim=True,
                acquired_gap=None,
                processed_gap=None,
            )
        )


def test_gap_may_be_negative() -> None:
    """Holding more than the source publishes is a finding, not a validation error.

    `ge=0` here would clamp away a dedup failure, or a denominator that counts something
    other than what we capture — the exact conditions this endpoint exists to expose.
    """
    entry = AcquisitionCoverageEntry(
        **_entry(acquired_distinct_urls=1400, acquired_gap=-23, processed_gap=-20)
    )
    assert entry.acquired_gap == -23


def test_counts_may_not_be_negative() -> None:
    with pytest.raises(ValidationError):
        AcquisitionCoverageEntry(**_entry(acquired_distinct_urls=-1))


class TestWorkActionAndActor:
    """#964 — one mapping, and an autonomy boundary that no ordering can move.

    The reason -> action mapping used to live only in `tools/evidara-cli`. A second
    client deriving it from the queue's own sort order classified
    `refusals_outstanding` + `never_acquired` — the normal shape of a refusal, every
    run refused so nothing acquired — as work the agent may do.
    """

    def test_every_reason_maps_to_an_action(self):
        """`resolve_work_action` raises rather than guessing, so an unmapped reason
        would be a 500 in production. This is what keeps that unreachable."""
        mapped = {reason for reason, _ in REASON_ACTION_PRIORITY}
        assert mapped == set(CoverageWorkReason), (
            "every CoverageWorkReason must map to an action; unmapped: "
            f"{sorted(r.value for r in set(CoverageWorkReason) - mapped)}"
        )

    @pytest.mark.parametrize(
        "reasons",
        [
            pytest.param([CoverageWorkReason.REFUSALS_OUTSTANDING], id="refusal-alone"),
            pytest.param(
                [CoverageWorkReason.REFUSALS_OUTSTANDING, CoverageWorkReason.NEVER_ACQUIRED],
                id="the-964-case",
            ),
            pytest.param(
                [CoverageWorkReason.NO_DENOMINATOR, CoverageWorkReason.REFUSALS_OUTSTANDING],
                id="refusal-behind-a-more-blocking-reason",
            ),
            pytest.param(
                [CoverageWorkReason.ACQUISITION_GAP, CoverageWorkReason.REFUSALS_OUTSTANDING],
                id="refusal-behind-a-gap",
            ),
        ],
    )
    def test_a_refusal_anywhere_makes_the_item_human_only(self, reasons):
        """The guard. `resolve_work_actor` folds over EVERY reason rather than the
        first that matches, so this holds whatever `REASON_ACTION_PRIORITY`'s order
        is. Change it to `resolve_work_action(...) in HUMAN_ONLY_ACTIONS` and the
        `refusal-behind-a-more-blocking-reason` case goes red — which is exactly the
        first-match rule that produced #964."""
        assert resolve_work_actor(reasons) is CoverageWorkActor.HUMAN

    def test_reordering_the_action_priority_cannot_grant_the_agent_a_refusal(self):
        """Mutation-resistance, stated as a test rather than left to review.

        Every non-empty subset containing a human-only reason must be human, under
        every rotation of the priority tuple.
        """
        import itertools

        human_reasons = [
            CoverageWorkReason.REFUSALS_OUTSTANDING,
            CoverageWorkReason.HOLDINGS_EXCEED_DENOMINATOR,
            CoverageWorkReason.NO_SOURCE,
        ]
        others = [r for r in CoverageWorkReason if r not in human_reasons]
        for human in human_reasons:
            for size in range(0, len(others) + 1):
                for combo in itertools.combinations(others, size):
                    assert resolve_work_actor([human, *combo]) is CoverageWorkActor.HUMAN

    def test_a_purely_agent_set_is_agent(self):
        """The guard must not be trivially satisfied by answering HUMAN always."""
        assert (
            resolve_work_actor(
                [CoverageWorkReason.NEVER_ACQUIRED, CoverageWorkReason.ACQUISITION_GAP]
            )
            is CoverageWorkActor.AGENT
        )
        assert resolve_work_actor([CoverageWorkReason.PROCESSING_GAP]) is CoverageWorkActor.AGENT

    def test_the_sort_order_and_the_action_order_are_allowed_to_differ(self):
        """They answer different questions and both are correct — but the CLI's
        comment claimed they were the same, which is how #964 happened. Pinned so a
        future reader sees the difference is deliberate, not drift."""
        from platform_control.services.coverage_service import _WORK_REASON_ORDER

        action_order = [reason for reason, _ in REASON_ACTION_PRIORITY]
        assert list(_WORK_REASON_ORDER) != action_order
        assert set(_WORK_REASON_ORDER) == set(action_order), (
            "they may order differently, but neither may omit a reason"
        )


class TestRegisterSourceSplit:
    """`register_source` was one action doing two jobs.

    The rationale in `HUMAN_ONLY_ACTIONS` said it "needs a deploy, which no queue
    action can express" — true when no blueprint template names the jurisdiction, and
    false when one does, where creating a source is an API call against a blueprint an
    author already wrote. The judgement (which portal, which provider, which trust
    tier) was made at authoring time, not at registration time.
    """

    def test_no_template_stays_human(self):
        assert (
            resolve_work_action([CoverageWorkReason.NO_SOURCE])
            is CoverageWorkAction.REGISTER_SOURCE
        )
        assert resolve_work_actor([CoverageWorkReason.NO_SOURCE]) is CoverageWorkActor.HUMAN

    def test_a_template_makes_it_agent_work(self):
        reasons = [CoverageWorkReason.NO_SOURCE_TEMPLATE_AVAILABLE]
        assert resolve_work_action(reasons) is CoverageWorkAction.REGISTER_SOURCE_FROM_TEMPLATE
        assert resolve_work_actor(reasons) is CoverageWorkActor.AGENT

    def test_the_agent_never_gets_the_deploy_variant(self):
        """The half that needs a repo edit must stay human however it is combined."""
        assert CoverageWorkAction.REGISTER_SOURCE in HUMAN_ONLY_ACTIONS
        assert CoverageWorkAction.REGISTER_SOURCE_FROM_TEMPLATE not in HUMAN_ONLY_ACTIONS

    def test_a_human_only_reason_alongside_still_wins(self):
        """The actor folds over EVERY reason (#964), so the new agent-actionable
        reason cannot launder a refusal into agent work by being named first."""
        reasons = [
            CoverageWorkReason.NO_SOURCE_TEMPLATE_AVAILABLE,
            CoverageWorkReason.REFUSALS_OUTSTANDING,
        ]
        assert resolve_work_actor(reasons) is CoverageWorkActor.HUMAN

    def test_both_halves_are_mapped(self):
        """`resolve_work_action` raises for an unmapped reason rather than guessing,
        so an unmapped new reason would fail loudly — asserted here anyway because
        the pair is the point of this change."""
        mapped = {reason for reason, _ in REASON_ACTION_PRIORITY}
        assert CoverageWorkReason.NO_SOURCE in mapped
        assert CoverageWorkReason.NO_SOURCE_TEMPLATE_AVAILABLE in mapped
