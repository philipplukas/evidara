"""ADR-0054 D4 — the abstention gate for sparse retrieval.

WHY THIS EXISTS
---------------
BM25 abstains for free: a query with no lexical overlap returns nothing, and
"no results" is a true statement about the corpus. Learned-sparse retrieval does
not. Measured against the live write alias on 2026-09-10 (see
`tests/fixtures/sparse_gate_calibration.json`, 24 queries), **every one of 24
queries returned every document that carries a sparse vector** — including
"recipe for chocolate cake", for which BM25 correctly returned zero hits.

That is #891, and it is ADR-0033's failure mode exactly: a legal-research system
that answers "here are 2 documents" to a question its corpus cannot address is
worse than one that refuses.

WHAT ADR-0054 D4 SPECIFIES, AND WHAT THIS IMPLEMENTS
----------------------------------------------------
D4 names two refusal conditions and nothing else:

  1. **Absolute floor** — the top fused score is below a threshold.
  2. **Margin collapse** — the top-K scores are indistinguishable from each
     other, which is what "nearest neighbours of an unrelated query" looks like.

Both are implemented here. Only the floor is *active by default*, because only
the floor has been calibrated against measured data; see `MARGIN_UNCALIBRATED`
below and `GateDecision.not_evaluated`, which reports the withheld rule rather
than letting it read as passing. AGENTS.md: an assertion that reports "not
applicable" is only honest if something else asserts the case it declined — the
floor asserts every case the margin rule declines.

D4 also says the threshold is *"a versioned knob (D2) with its own regression
case, not a constant someone picked"*. `GateConfig.version` is that version and
`CALIBRATION` is the evidence behind each knob.

WHY THE FLOOR IS ON A RATIO AND NOT ON THE RAW SCORE
---------------------------------------------------
ADR-0042: every number needs a denominator. A raw `rank_feature` score is a sum
over the query's feature weights, so it scales with how much weight mass the
query carries — a long query scores higher than a short one on the same
document. The measured consequence is in the calibration fixture: on **raw top
score** the in-corpus and out-of-corpus populations *overlap* (lowest in-corpus
0.11523, highest out-of-corpus 0.13840), so no raw floor can separate them at
all. Dividing by the query's weight mass — "how much of what the query asked for
did the best document actually carry" — is what makes a floor possible.

A query with zero weight mass has no denominator. The gate refuses it
(`UNSCORABLE`) rather than dividing by zero or substituting a number it did not
measure.

THE THING THIS GATE REPORTS AND DELIBERATELY DOES NOT GATE ON
-------------------------------------------------------------
`GateDecision.matched_whole_corpus` records whether the retriever returned every
searchable document — the #891 signature. It is *reported*, never a third
refusal condition, because D4 specifies two and inventing a third here would be
exactly the "do not invent your own semantics" failure. It is `None`, not
`False`, when the corpus size was not supplied: unknown is not zero (ADR-0052).
"""

from __future__ import annotations

from collections.abc import Sequence
from dataclasses import dataclass, field
from enum import StrEnum
from typing import Any

#: Bumped whenever any knob below changes. ADR-0054 D2: without it a relevance
#: number cannot be attributed to a configuration and A/B results become folklore.
RETRIEVAL_CONFIG_VERSION = "sparse-gate-2026-09-10"

#: Why the margin rule ships inactive. There is no corpus to calibrate it
#: against: the live index holds three copies of the same Bundesverfassung
#: (#806), so every query's top-K scores are identical by construction and a
#: margin rule calibrated on it would refuse everything, forever.
MARGIN_UNCALIBRATED = (
    "margin collapse is specified by ADR-0054 D4 but ships inactive: the serving "
    "corpus is duplicates of one document (#806), so top-K scores are identical for "
    "every query and the knob cannot be calibrated. Enable it with "
    "GateConfig(margin_enabled=True, ...) once a corpus with distinct documents exists."
)


#: What the default floor was chosen against, and — the part that matters —
#: what it lets through. ADR-0042: a number without a denominator is not a
#: measurement. `test_embedding_gating.py` recomputes every count here from
#: `tests/fixtures/sparse_gate_calibration.json` and fails if the claim drifts,
#: so this block cannot become folklore.
CALIBRATION: dict[str, Any] = {
    "fixture": "tests/fixtures/sparse_gate_calibration.json",
    "measured_at": "2026-09-10",
    "queries": 24,
    "in_corpus": 12,
    "out_of_corpus": 12,
    # The reason the floor is on `coverage` and not on the raw score.
    "raw_score_separates": False,
    "raw_score_lowest_in_corpus": 0.11523,
    "raw_score_highest_out_of_corpus": 0.13840,
    # At coverage_floor = 0.08.
    "in_corpus_admitted": 12,
    "out_of_corpus_refused": 10,
    "out_of_corpus_admitted": [
        "Aufstellung Champions League Finale 1999",
        "welche Bewilligung brauche ich fuer einen Kampfhund in Zuerich",
    ],
    # The floor is NOT set to the value that separates this fixture perfectly.
    # That value is ~0.105, and it sits 0.001 below a genuine in-corpus query
    # ("Wer waehlt die Bundesrichter?", coverage 0.10535). AGENTS.md's fixture
    # trap, arrived at from measurement rather than from the warning: a floor
    # tuned to one sample withholds real answers on the next one.
    "perfect_separation_floor_rejected": 0.105,
    "closest_in_corpus_coverage": 0.10535,
    # ADR-0033's acceptance test, second half: the dog question is correctly
    # refused here because the ordinance is not in this corpus.
    "dog_question_refused": "darf ich meinen Hund im Restaurant mitnehmen",
    "dog_question_coverage": 0.04179,
}


class RefusalReason(StrEnum):
    """Why the gate withheld results. Never collapsed into an empty list."""

    #: Nothing matched at all. "No result" — a true statement about the corpus.
    NO_CANDIDATES = "no_candidates"
    #: Things matched, but nothing matched *enough*. This is the "every result"
    #: case: the retriever returned documents because it always returns
    #: documents, not because any of them answers the query.
    BELOW_FLOOR = "below_floor"
    #: The top-K scores are indistinguishable — ADR-0054 D4's second condition.
    MARGIN_COLLAPSE = "margin_collapse"
    #: The gate could not score the result set. Refusing is the only honest
    #: answer; passing would mean admitting results on a number nobody measured.
    UNSCORABLE = "unscorable"


@dataclass(frozen=True)
class Candidate:
    """One scored retrieval candidate."""

    document_id: str
    score: float


@dataclass(frozen=True)
class GateConfig:
    """ADR-0054 D2's versioned knob object for stage 4.

    Every field here is a knob, and `version` must change when any of them does.
    """

    version: str = RETRIEVAL_CONFIG_VERSION

    #: Floor on `top_score / query_weight_mass`. See CALIBRATION for the measured
    #: distribution this was chosen against and for what it lets through.
    coverage_floor: float = 0.08

    #: How many top candidates the margin rule inspects. ADR-0054 D4's "top-K".
    margin_top_k: int = 10

    #: Relative spread below which the top-K are called indistinguishable:
    #: (top1 - topK) / top1.
    margin_min_spread: float = 0.05

    #: The margin rule needs at least this many candidates to have any power. Two
    #: candidates cannot tell "indistinguishable" from "a two-document corpus".
    margin_min_candidates: int = 3

    #: Off by default — see MARGIN_UNCALIBRATED. Not silently off: a decision
    #: taken with it off carries the reason in `not_evaluated`.
    margin_enabled: bool = False

    #: How many admitted results to return.
    top_n: int = 10


@dataclass(frozen=True)
class GateDecision:
    """The outcome of stage 4. A refusal is a state, not an empty list."""

    admitted: bool
    results: list[Candidate]
    refusal_reason: RefusalReason | None
    #: Human-readable, operator-facing. Always populated on a refusal.
    detail: str
    top_score: float | None
    query_weight_mass: float | None
    #: `top_score / query_weight_mass`. None when there is no denominator.
    coverage: float | None
    #: (top1 - topK) / top1 over the inspected window. None when not computable.
    margin_spread: float | None
    #: True when the retriever returned every searchable document — the #891
    #: signature. None when corpus size was not supplied: unknown is not zero.
    matched_whole_corpus: bool | None
    candidates_in: int
    #: Rules that actually ran, and rules that did not, with the reason. A gate
    #: that declines a rule must say so; a silent decline reads as a pass.
    evaluated: list[str] = field(default_factory=list)
    not_evaluated: list[tuple[str, str]] = field(default_factory=list)
    config_version: str = RETRIEVAL_CONFIG_VERSION

    def as_dict(self) -> dict[str, Any]:
        return {
            "admitted": self.admitted,
            "results": [{"document_id": c.document_id, "score": c.score} for c in self.results],
            "refusal_reason": self.refusal_reason.value if self.refusal_reason else None,
            "detail": self.detail,
            "top_score": self.top_score,
            "query_weight_mass": self.query_weight_mass,
            "coverage": self.coverage,
            "margin_spread": self.margin_spread,
            "matched_whole_corpus": self.matched_whole_corpus,
            "candidates_in": self.candidates_in,
            "evaluated": list(self.evaluated),
            "not_evaluated": [list(item) for item in self.not_evaluated],
            "config_version": self.config_version,
        }


def query_weight_mass(vector: dict[str, float]) -> float:
    """Total weight the query asked for — the denominator of `coverage`.

    Pass the vector **as sent to the search engine**. If the caller truncated it
    to the top-N features, the mass must be the mass of the truncated vector, or
    the ratio describes a query that was never issued.
    """
    return float(sum(vector.values()))


def gate(
    candidates: Sequence[Candidate],
    *,
    mass: float | None,
    corpus_size: int | None = None,
    config: GateConfig | None = None,
) -> GateDecision:
    """Apply ADR-0054 D4 to a scored candidate set.

    `mass` is the query's total sparse weight (`query_weight_mass`). `None` or a
    non-positive value means the result set cannot be scored, and the gate
    refuses rather than inventing a denominator.
    """
    cfg = config or GateConfig()
    ordered = sorted(candidates, key=lambda c: c.score, reverse=True)
    candidates_in = len(ordered)
    whole = None if corpus_size is None else (corpus_size > 0 and candidates_in >= corpus_size)

    def decide(
        *,
        admitted: bool,
        reason: RefusalReason | None,
        detail: str,
        results: list[Candidate],
        top_score: float | None,
        coverage: float | None,
        spread: float | None,
        evaluated: list[str],
        not_evaluated: list[tuple[str, str]],
    ) -> GateDecision:
        return GateDecision(
            admitted=admitted,
            results=results,
            refusal_reason=reason,
            detail=detail,
            top_score=top_score,
            query_weight_mass=mass,
            coverage=coverage,
            margin_spread=spread,
            matched_whole_corpus=whole,
            candidates_in=candidates_in,
            evaluated=evaluated,
            not_evaluated=not_evaluated,
            config_version=cfg.version,
        )

    if candidates_in == 0:
        # "No result" — distinct from "every result" below, and the caller must
        # be able to tell them apart (#891, and #551's axis).
        return decide(
            admitted=False,
            reason=RefusalReason.NO_CANDIDATES,
            detail="the retriever matched no document; the corpus contains nothing for this query",
            results=[],
            top_score=None,
            coverage=None,
            spread=None,
            evaluated=[],
            not_evaluated=[],
        )

    if mass is None or mass <= 0.0:
        return decide(
            admitted=False,
            reason=RefusalReason.UNSCORABLE,
            detail=(
                f"query weight mass is {mass!r}: the coverage ratio has no denominator, so the "
                "result set cannot be scored. Refusing rather than admitting results on an "
                "unmeasured number (ADR-0042)."
            ),
            results=[],
            top_score=ordered[0].score,
            coverage=None,
            spread=None,
            evaluated=[],
            not_evaluated=[("absolute_floor", "no denominator"), ("margin_collapse", "no denominator")],
        )

    top_score = ordered[0].score
    coverage = top_score / mass

    window = ordered[: cfg.margin_top_k]
    spread: float | None = None
    if window and window[0].score > 0.0:
        spread = (window[0].score - window[-1].score) / window[0].score

    evaluated = ["absolute_floor"]
    not_evaluated: list[tuple[str, str]] = []

    margin_runs = cfg.margin_enabled
    if not cfg.margin_enabled:
        not_evaluated.append(("margin_collapse", MARGIN_UNCALIBRATED))
    elif candidates_in < cfg.margin_min_candidates:
        margin_runs = False
        not_evaluated.append(
            (
                "margin_collapse",
                f"{candidates_in} candidate(s) is below margin_min_candidates="
                f"{cfg.margin_min_candidates}; the statistic has no power. The absolute "
                "floor still applies to this case.",
            )
        )
    else:
        evaluated.append("margin_collapse")

    if coverage < cfg.coverage_floor:
        return decide(
            admitted=False,
            reason=RefusalReason.BELOW_FLOOR,
            detail=(
                f"top coverage {coverage:.5f} is below the floor {cfg.coverage_floor} "
                f"(top score {top_score:.5f} over query weight mass {mass:.5f}). "
                f"{candidates_in} document(s) matched, which is what this retriever does for "
                "every query; none of them answers it."
            ),
            results=[],
            top_score=top_score,
            coverage=coverage,
            spread=spread,
            evaluated=evaluated,
            not_evaluated=not_evaluated,
        )

    if margin_runs and spread is not None and spread < cfg.margin_min_spread:
        return decide(
            admitted=False,
            reason=RefusalReason.MARGIN_COLLAPSE,
            detail=(
                f"the top {len(window)} scores span {spread:.5f} of the top score, below "
                f"margin_min_spread={cfg.margin_min_spread}: the ranking does not distinguish "
                "its own candidates, which is what nearest neighbours of an unrelated query "
                "look like."
            ),
            results=[],
            top_score=top_score,
            coverage=coverage,
            spread=spread,
            evaluated=evaluated,
            not_evaluated=not_evaluated,
        )

    return decide(
        admitted=True,
        reason=None,
        detail=f"coverage {coverage:.5f} clears the floor {cfg.coverage_floor}",
        results=list(ordered[: cfg.top_n]),
        top_score=top_score,
        coverage=coverage,
        spread=spread,
        evaluated=evaluated,
        not_evaluated=not_evaluated,
    )
