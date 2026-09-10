"""Tests for the sparse gate probe (ADR-0054 D4).

No model, no cluster. What is worth testing here is the wiring between the
encoder and the gate's denominator: the probe truncates the query vector before
sending it, so the mass it hands the gate must be the mass of the **truncated**
vector. Get that wrong and `coverage` is a ratio over a query that was never
issued — a number that reads as measured and is not (ADR-0042).
"""

from __future__ import annotations

import json

import pytest

from document_intelligence.embeddings.gating import GateConfig, RefusalReason
from document_intelligence.jobs.sparse_gate_probe import (
    SearchClient,
    build_parser,
    load_queries,
    probe_query,
)


class _FakeClient:
    def __init__(self, candidates, *, bm25: int = 0) -> None:
        self._candidates = candidates
        self._bm25 = bm25
        self.sent_vectors: list[dict[str, float]] = []

    def sparse_search(self, index, vector, *, size):
        self.sent_vectors.append(dict(vector))
        return list(self._candidates)

    def bm25_hits(self, index, query):
        return self._bm25


class _FakeEncoder:
    def __init__(self, vector) -> None:
        self._vector = vector

    def encode_query(self, text: str):
        return dict(self._vector)


def _probe(client, encoder, *, max_features=512, config=None, corpus_size=2):
    return probe_query(
        client,
        encoder,
        "darf ich meinen Hund im Restaurant mitnehmen",
        index="documents-write",
        corpus_size=corpus_size,
        max_features=max_features,
        config=config or GateConfig(),
    )


class TestTheDenominatorMatchesTheQueryActuallyIssued:
    def test_truncation_shrinks_both_the_query_and_its_mass(self) -> None:
        from document_intelligence.embeddings.gating import Candidate

        vector = {f"t{i}": 0.1 for i in range(10)}
        client = _FakeClient([Candidate("a", 0.05)])
        decision, context = _probe(client, _FakeEncoder(vector), max_features=3)

        assert len(client.sent_vectors[0]) == 3
        assert decision.query_weight_mass == pytest.approx(0.3)
        assert context["query_features"] == 3
        assert context["query_features_before_truncation"] == 10

    def test_the_full_vector_mass_would_have_given_a_different_verdict(self) -> None:
        """The bug this guards: dividing by the untruncated mass.

        Same candidates, same truncation — the coverage over the sent mass
        clears the floor, and the coverage over the full mass does not.
        """
        from document_intelligence.embeddings.gating import Candidate, gate

        vector = {f"t{i}": 0.1 for i in range(10)}
        client = _FakeClient([Candidate("a", 0.05)])
        decision, _ = _probe(client, _FakeEncoder(vector), max_features=3)
        assert decision.admitted is True

        wrong = gate([Candidate("a", 0.05)], mass=sum(vector.values()), corpus_size=2)
        assert wrong.admitted is False
        assert wrong.refusal_reason is RefusalReason.BELOW_FLOOR

    def test_an_empty_query_vector_is_unscorable_not_empty(self) -> None:
        client = _FakeClient([])
        decision, _ = _probe(client, _FakeEncoder({}))
        # No features to send means no search was possible at all — the probe
        # must not report that as "the corpus has nothing".
        assert decision.refusal_reason is RefusalReason.NO_CANDIDATES
        assert client.sent_vectors == [{}]


class TestTheProbeReportsTheContrast:
    def test_bm25_hits_travel_with_the_decision(self) -> None:
        from document_intelligence.embeddings.gating import Candidate

        client = _FakeClient([Candidate("a", 0.003), Candidate("b", 0.003)], bm25=0)
        decision, context = _probe(client, _FakeEncoder({"t1": 1.0}))
        assert context["bm25_hits"] == 0
        assert decision.candidates_in == 2
        assert decision.matched_whole_corpus is True
        assert decision.refusal_reason is RefusalReason.BELOW_FLOOR


class TestQueryLoading:
    def test_labels_are_carried_from_the_calibration_fixture(self, tmp_path) -> None:
        path = tmp_path / "q.json"
        path.write_text(
            json.dumps({"queries": [{"label": "OUT", "query": "recipe for chocolate cake"}]}),
            encoding="utf-8",
        )
        args = build_parser().parse_args(["--queries-file", str(path)])
        assert load_queries(args) == [("OUT", "recipe for chocolate cake")]

    def test_inline_queries_have_no_ground_truth_label(self) -> None:
        args = build_parser().parse_args(["--query", "a", "--query", "b"])
        assert load_queries(args) == [(None, "a"), (None, "b")]

    def test_the_committed_calibration_fixture_loads(self) -> None:
        from pathlib import Path

        fixture = Path(__file__).parent / "fixtures" / "sparse_gate_calibration.json"
        args = build_parser().parse_args(["--queries-file", str(fixture)])
        pairs = load_queries(args)
        assert len(pairs) == 24
        assert {label for label, _ in pairs} == {"IN", "OUT"}


class TestTheSparseQueryShape:
    def test_features_become_rank_feature_clauses_on_the_sparse_field(self) -> None:
        """The clause shape is what the calibration was measured with.

        A different shape produces different scores, and a floor calibrated on
        one shape says nothing about the other.
        """
        captured: dict = {}

        class _Recording(SearchClient):
            def _post(self, path, body):
                captured["path"] = path
                captured["body"] = body
                return {"hits": {"hits": []}}

        _Recording("http://x").sparse_search("documents-write", {"t42": 0.25}, size=10)
        clause = captured["body"]["query"]["bool"]["should"][0]["rank_feature"]
        assert clause["field"] == "content_sparse.t42"
        assert clause["boost"] == 0.25
        assert clause["linear"] == {}

    def test_no_features_means_no_request_is_issued(self) -> None:
        class _Exploding(SearchClient):
            def _post(self, path, body):  # pragma: no cover - must not be reached
                raise AssertionError("a featureless query must not be sent")

        assert _Exploding("http://x").sparse_search("documents-write", {}, size=10) == []
