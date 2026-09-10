"""ADR-0054 D4 — the abstention gate, and the measured data it is calibrated on.

Nothing here loads a model or reaches a cluster. The measurement that motivates
the gate is committed as `fixtures/sparse_gate_calibration.json` — 24 queries run
against the live write alias on 2026-09-10 — and replayed through the pure gate,
so the calibration is a fixture in CI rather than a memory of a terminal session.

THE MUTATION THESE TESTS ARE BUILT TO CATCH
-------------------------------------------
Delete the floor (`coverage_floor = 0.0`, or drop the `coverage < floor` branch)
and these go red:

  - test_out_of_corpus_queries_are_refused_at_the_default_floor
  - test_the_891_measurement_is_refused
  - test_the_dog_question_is_refused_because_the_ordinance_is_not_in_this_corpus
  - test_calibration_block_matches_the_fixture

Delete the margin rule and `test_margin_collapse_refuses_a_flat_ranking` and
`test_margin_min_spread_changes_the_answer` go red.
"""

from __future__ import annotations

import json
from pathlib import Path

import pytest

from document_intelligence.embeddings.gating import (
    CALIBRATION,
    MARGIN_UNCALIBRATED,
    RETRIEVAL_CONFIG_VERSION,
    Candidate,
    GateConfig,
    RefusalReason,
    gate,
    query_weight_mass,
)

FIXTURE = Path(__file__).parent / "fixtures" / "sparse_gate_calibration.json"


def _calibration() -> dict:
    return json.loads(FIXTURE.read_text(encoding="utf-8"))


def _rows() -> list[dict]:
    return _calibration()["queries"]


def _row(query: str) -> dict:
    for row in _rows():
        if row["query"] == query:
            return row
    raise AssertionError(f"no calibration row for {query!r}")


def _decide(row: dict, config: GateConfig | None = None):
    """Replay one measured row through the gate exactly as a serving path would."""
    candidates = [Candidate(f"doc_{i}", score) for i, score in enumerate(row["sparse_scores"])]
    return gate(
        candidates,
        mass=row["query_weight_mass"],
        corpus_size=_calibration()["provenance"]["searchable_documents"],
        config=config,
    )


class TestTheMeasuredDefect:
    """#891, as data rather than as a claim."""

    def test_sparse_retrieval_returned_every_searchable_document_for_every_query(self) -> None:
        searchable = _calibration()["provenance"]["searchable_documents"]
        rows = _rows()
        assert len(rows) == 24
        assert all(row["sparse_hits"] == searchable for row in rows), (
            "the premise of #891: sparse retrieval never abstains, so it returns the whole "
            "searchable corpus for every query including the unrelated ones"
        )

    def test_bm25_abstained_where_sparse_did_not(self) -> None:
        abstained = [row for row in _rows() if row["bm25_hits"] == 0]
        assert abstained, "no BM25 abstention in the fixture — the contrast #891 rests on is gone"
        assert all(row["sparse_hits"] > 0 for row in abstained)

    def test_the_891_measurement_is_refused(self) -> None:
        row = _row("recipe for chocolate cake")
        assert row["bm25_hits"] == 0
        assert row["sparse_hits"] == 2
        decision = _decide(row)
        assert decision.admitted is False
        assert decision.refusal_reason is RefusalReason.BELOW_FLOOR
        assert decision.results == []
        # It must say *which* failure this is: everything matched, not nothing did.
        assert decision.matched_whole_corpus is True
        assert "matched" in decision.detail

    def test_the_dog_question_is_refused_because_the_ordinance_is_not_in_this_corpus(self) -> None:
        """ADR-0033's acceptance test, second half.

        This corpus is three copies of the Bundesverfassung. A ZH dog-ordinance
        question has no answer in it, and the honest response is a refusal.
        """
        decision = _decide(_row("darf ich meinen Hund im Restaurant mitnehmen"))
        assert decision.admitted is False
        assert decision.refusal_reason is RefusalReason.BELOW_FLOOR


class TestTheFloorAgainstTheMeasuredDistribution:
    def test_in_corpus_queries_are_admitted_at_the_default_floor(self) -> None:
        admitted = [row["query"] for row in _rows() if row["label"] == "IN" and _decide(row).admitted]
        assert len(admitted) == 12, "the floor withholds a genuine answer"

    def test_out_of_corpus_queries_are_refused_at_the_default_floor(self) -> None:
        refused = [row["query"] for row in _rows() if row["label"] == "OUT" and not _decide(row).admitted]
        assert len(refused) == CALIBRATION["out_of_corpus_refused"] == 10

    def test_the_floor_lets_two_out_of_corpus_queries_through_and_says_which(self) -> None:
        """The gate is not claimed to be perfect, and the leak is named.

        A gate reported as clean would be the folklore ADR-0054 D2 exists to
        prevent. Two out-of-corpus queries clear a floor of 0.08 — one of them a
        legally-worded German question about Zurich dog licensing, which is the
        hard case and the one a bigger corpus has to solve, not a threshold.
        """
        leaked = sorted(row["query"] for row in _rows() if row["label"] == "OUT" and _decide(row).admitted)
        assert leaked == sorted(CALIBRATION["out_of_corpus_admitted"])

    def test_a_raw_score_floor_could_not_separate_these_populations(self) -> None:
        """Why the floor is on a ratio: on raw score the populations overlap."""
        lowest_in = min(row["sparse_top"] for row in _rows() if row["label"] == "IN")
        highest_out = max(row["sparse_top"] for row in _rows() if row["label"] == "OUT")
        assert lowest_in < highest_out
        assert CALIBRATION["raw_score_separates"] is False

    def test_calibration_block_matches_the_fixture(self) -> None:
        """The numbers in the module docstring's calibration block are recomputed.

        Without this the block is a comment, and a comment cannot go stale
        loudly.
        """
        rows = _rows()
        assert CALIBRATION["queries"] == len(rows)
        assert CALIBRATION["in_corpus"] == sum(1 for r in rows if r["label"] == "IN")
        assert CALIBRATION["out_of_corpus"] == sum(1 for r in rows if r["label"] == "OUT")
        assert CALIBRATION["in_corpus_admitted"] == sum(1 for r in rows if r["label"] == "IN" and _decide(r).admitted)
        assert CALIBRATION["out_of_corpus_refused"] == sum(
            1 for r in rows if r["label"] == "OUT" and not _decide(r).admitted
        )
        closest = min(r["coverage"] for r in rows if r["label"] == "IN")
        assert CALIBRATION["closest_in_corpus_coverage"] == pytest.approx(closest, abs=1e-5)
        assert CALIBRATION["dog_question_coverage"] == pytest.approx(
            _row(CALIBRATION["dog_question_refused"])["coverage"], abs=1e-5
        )


class TestTheFixtureTrap:
    """A floor tuned to this one sample withholds real answers.

    AGENTS.md: "a marker floor of 3 put two genuine in-force municipal
    ordinances exactly on the boundary". Same shape, measured here.
    """

    def test_the_perfectly_separating_floor_sits_one_thousandth_from_a_real_query(self) -> None:
        lowest_in = min(row["coverage"] for row in _rows() if row["label"] == "IN")
        highest_out = max(row["coverage"] for row in _rows() if row["label"] == "OUT")
        assert highest_out < lowest_in
        assert lowest_in - highest_out < 0.002, (
            "a floor placed in this gap is tuned to 24 queries against a 2-document corpus"
        )
        assert CALIBRATION["perfect_separation_floor_rejected"] > highest_out

    def test_a_wrong_threshold_gives_a_different_answer(self) -> None:
        """The test the guard would be decoration without.

        The same genuine in-corpus query is admitted at the shipped floor and
        refused at the tempting one. If the gate's answer did not move with the
        knob, the knob would not be doing anything.
        """
        row = _row("Wer waehlt die Bundesrichter?")
        assert _decide(row, GateConfig(coverage_floor=0.08)).admitted is True
        tuned = _decide(row, GateConfig(coverage_floor=0.11))
        assert tuned.admitted is False
        assert tuned.refusal_reason is RefusalReason.BELOW_FLOOR

    def test_a_floor_of_zero_admits_everything_including_the_chocolate_cake(self) -> None:
        """Deleting the floor is the same as setting it to zero, and it is visible."""
        no_floor = GateConfig(coverage_floor=0.0)
        assert all(_decide(row, no_floor).admitted for row in _rows())


class TestNoResultVersusEveryResult:
    def test_an_empty_candidate_set_is_no_candidates_not_below_floor(self) -> None:
        decision = gate([], mass=1.0, corpus_size=2)
        assert decision.refusal_reason is RefusalReason.NO_CANDIDATES
        assert decision.matched_whole_corpus is False
        assert decision.top_score is None

    def test_a_whole_corpus_match_below_the_floor_is_below_floor(self) -> None:
        decision = gate(
            [Candidate("a", 0.003), Candidate("b", 0.003)],
            mass=1.0,
            corpus_size=2,
        )
        assert decision.refusal_reason is RefusalReason.BELOW_FLOOR
        assert decision.matched_whole_corpus is True

    def test_the_two_refusals_are_distinguishable(self) -> None:
        nothing = gate([], mass=1.0, corpus_size=2)
        everything = gate([Candidate("a", 0.001), Candidate("b", 0.001)], mass=1.0, corpus_size=2)
        assert nothing.refusal_reason is not everything.refusal_reason
        assert nothing.detail != everything.detail

    def test_unknown_corpus_size_is_none_not_false(self) -> None:
        """ADR-0052: unknown is not zero, and it is not `False` either."""
        decision = gate([Candidate("a", 0.5)], mass=1.0)
        assert decision.matched_whole_corpus is None


class TestRefusingToScore:
    def test_zero_weight_mass_refuses_rather_than_dividing_by_zero(self) -> None:
        decision = gate([Candidate("a", 0.2)], mass=0.0, corpus_size=2)
        assert decision.admitted is False
        assert decision.refusal_reason is RefusalReason.UNSCORABLE
        assert decision.coverage is None
        assert "denominator" in decision.detail

    def test_missing_weight_mass_refuses(self) -> None:
        decision = gate([Candidate("a", 0.2)], mass=None, corpus_size=2)
        assert decision.refusal_reason is RefusalReason.UNSCORABLE

    def test_an_unscorable_decision_names_both_rules_it_could_not_run(self) -> None:
        decision = gate([Candidate("a", 0.2)], mass=0.0)
        assert [rule for rule, _ in decision.not_evaluated] == ["absolute_floor", "margin_collapse"]
        assert decision.evaluated == []

    def test_query_weight_mass_is_the_sum_of_the_vector_actually_sent(self) -> None:
        assert query_weight_mass({"t1": 0.25, "t2": 0.75}) == pytest.approx(1.0)
        assert query_weight_mass({}) == 0.0


class TestMarginCollapse:
    def test_margin_is_not_evaluated_by_default_and_says_why(self) -> None:
        """The rule ADR-0054 D4 specifies but this corpus cannot calibrate.

        Reported, not silent: a rule that declines without saying so reads as a
        rule that passed.
        """
        decision = gate([Candidate("a", 0.5), Candidate("b", 0.5)], mass=1.0, corpus_size=2)
        assert "margin_collapse" not in decision.evaluated
        reasons = dict(decision.not_evaluated)
        assert reasons["margin_collapse"] == MARGIN_UNCALIBRATED
        assert "#806" in MARGIN_UNCALIBRATED

    def test_margin_collapse_refuses_a_flat_ranking(self) -> None:
        flat = [Candidate(f"d{i}", 0.5) for i in range(5)]
        decision = gate(flat, mass=1.0, corpus_size=10, config=GateConfig(margin_enabled=True))
        assert decision.admitted is False
        assert decision.refusal_reason is RefusalReason.MARGIN_COLLAPSE
        assert decision.margin_spread == pytest.approx(0.0)

    def test_a_ranking_that_discriminates_is_admitted(self) -> None:
        graded = [Candidate("a", 0.9), Candidate("b", 0.4), Candidate("c", 0.1)]
        decision = gate(graded, mass=1.0, corpus_size=10, config=GateConfig(margin_enabled=True))
        assert decision.admitted is True
        assert "margin_collapse" in decision.evaluated

    def test_margin_min_spread_changes_the_answer(self) -> None:
        """The knob is load-bearing: same candidates, two thresholds, two answers."""
        candidates = [Candidate("a", 1.0), Candidate("b", 0.94), Candidate("c", 0.93)]
        lenient = gate(candidates, mass=1.0, config=GateConfig(margin_enabled=True, margin_min_spread=0.05))
        strict = gate(candidates, mass=1.0, config=GateConfig(margin_enabled=True, margin_min_spread=0.20))
        assert lenient.admitted is True
        assert strict.admitted is False
        assert strict.refusal_reason is RefusalReason.MARGIN_COLLAPSE

    def test_margin_declines_on_too_few_candidates_and_the_floor_still_applies(self) -> None:
        """The declined case is asserted by something else, per AGENTS.md."""
        config = GateConfig(margin_enabled=True)
        two_flat_weak = gate([Candidate("a", 0.01), Candidate("b", 0.01)], mass=1.0, corpus_size=2, config=config)
        assert "margin_collapse" not in two_flat_weak.evaluated
        assert dict(two_flat_weak.not_evaluated)["margin_collapse"].startswith("2 candidate(s)")
        assert two_flat_weak.refusal_reason is RefusalReason.BELOW_FLOOR

    def test_the_floor_runs_before_the_margin(self) -> None:
        """A weak flat set is reported as weak, not as undiscriminating.

        Both are true; the floor is the one an operator can act on.
        """
        weak_flat = [Candidate(f"d{i}", 0.001) for i in range(5)]
        decision = gate(weak_flat, mass=1.0, corpus_size=5, config=GateConfig(margin_enabled=True))
        assert decision.refusal_reason is RefusalReason.BELOW_FLOOR


class TestTheDecisionIsAttributable:
    def test_every_decision_carries_the_config_version(self) -> None:
        for decision in (
            gate([], mass=1.0),
            gate([Candidate("a", 0.9)], mass=1.0),
            gate([Candidate("a", 0.001)], mass=1.0),
            gate([Candidate("a", 0.9)], mass=0.0),
        ):
            assert decision.config_version == RETRIEVAL_CONFIG_VERSION

    def test_a_custom_config_stamps_its_own_version(self) -> None:
        decision = gate([Candidate("a", 0.9)], mass=1.0, config=GateConfig(version="experiment-7"))
        assert decision.config_version == "experiment-7"

    def test_as_dict_is_serialisable_and_keeps_the_refusal_reason(self) -> None:
        payload = gate([Candidate("a", 0.001)], mass=1.0, corpus_size=1).as_dict()
        assert json.loads(json.dumps(payload))["refusal_reason"] == "below_floor"
        assert payload["config_version"] == RETRIEVAL_CONFIG_VERSION

    def test_admitted_results_are_ordered_and_capped(self) -> None:
        candidates = [Candidate(f"d{i}", 1.0 - i * 0.05) for i in range(20)]
        decision = gate(candidates, mass=1.0, config=GateConfig(top_n=3))
        assert [c.document_id for c in decision.results] == ["d0", "d1", "d2"]

    def test_a_refusal_never_returns_results(self) -> None:
        for decision in (
            gate([], mass=1.0),
            gate([Candidate("a", 0.001)], mass=1.0),
            gate([Candidate("a", 0.9)], mass=0.0),
            gate([Candidate(f"d{i}", 0.5) for i in range(5)], mass=1.0, config=GateConfig(margin_enabled=True)),
        ):
            if not decision.admitted:
                assert decision.results == []
                assert decision.detail
