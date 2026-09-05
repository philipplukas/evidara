"""Tests for the sparse backfill job (ADR-0054).

The refusals matter more than the happy path here. This job writes to the
documents index, and the two ways that goes wrong silently are: writing a field
the mapping does not have (which OpenSearch accepts by dynamic-mapping it into a
shape nothing agreed to), and writing an empty `rank_features` map (a document
that can never match, wearing the shape of one that simply does not).
"""

from __future__ import annotations

import pytest

from document_intelligence.jobs.embedding_backfill import (
    SPARSE_FIELD,
    BackfillReport,
    run_backfill,
)


class _FakeClient:
    def __init__(self, hits, *, has_field: bool = True, bulk_failures=None) -> None:
        self._hits = hits
        self._has_field = has_field
        self._bulk_failures = bulk_failures or []
        self.updates: list[tuple[str, dict]] = []
        self.bulk_calls = 0

    def mapping_has_sparse_field(self, index: str) -> bool:
        return self._has_field

    def scroll_documents(self, index: str, *, page_size: int, limit):
        return self._hits if limit is None else self._hits[:limit]

    def bulk_update(self, index: str, updates):
        self.bulk_calls += 1
        self.updates.extend(updates)
        return list(self._bulk_failures)


class _FakeEncoder:
    def __init__(self, vectors=None) -> None:
        self._vectors = vectors

    def encode_documents(self, texts, *, batch_size: int = 4):
        if self._vectors is not None:
            return self._vectors[: len(texts)]
        return [{"t1": 0.5} for _ in texts]


def _hit(doc_id: str, content):
    return {"_id": doc_id, "_source": {"document_id": doc_id, "content": content}}


def _run(client, encoder, **kwargs):
    params = dict(index="documents-write", page_size=100, batch_size=4, limit=None, dry_run=False)
    params.update(kwargs)
    return run_backfill(client, encoder, **params)


class TestMappingRefusal:
    def test_it_refuses_an_index_that_does_not_map_the_field(self) -> None:
        """The guard that stops this job dynamic-mapping a field it does not own."""
        client = _FakeClient([_hit("doc_1", "text")], has_field=False)
        with pytest.raises(RuntimeError, match="does not map"):
            _run(client, _FakeEncoder())

    def test_it_writes_nothing_when_it_refuses(self) -> None:
        client = _FakeClient([_hit("doc_1", "text")], has_field=False)
        with pytest.raises(RuntimeError):
            _run(client, _FakeEncoder())
        assert client.updates == []
        assert client.bulk_calls == 0


class TestContentHandling:
    def test_documents_without_content_are_skipped_and_named(self) -> None:
        client = _FakeClient([_hit("doc_1", None), _hit("doc_2", "  "), _hit("doc_3", "real")])
        report = _run(client, _FakeEncoder())
        assert report.skipped_no_content == ["doc_1", "doc_2"]
        assert report.embedded == 1
        assert [doc_id for doc_id, _ in client.updates] == ["doc_3"]

    def test_an_empty_vector_is_a_failure_not_a_write(self) -> None:
        """Writing `{}` would index a document that can never match a sparse query."""
        client = _FakeClient([_hit("doc_1", "text")])
        report = _run(client, _FakeEncoder(vectors=[{}]))
        assert client.updates == []
        assert report.updated == 0
        assert len(report.failed) == 1
        assert "empty sparse vector" in report.failed[0]


class TestWrites:
    def test_it_updates_only_the_sparse_field(self) -> None:
        """A full `index` would overwrite a projection written by live traffic."""
        client = _FakeClient([_hit("doc_1", "text")])
        _run(client, _FakeEncoder())
        assert client.updates == [("doc_1", {SPARSE_FIELD: {"t1": 0.5}})]

    def test_dry_run_encodes_but_writes_nothing(self) -> None:
        client = _FakeClient([_hit("doc_1", "text")])
        report = _run(client, _FakeEncoder(), dry_run=True)
        assert client.bulk_calls == 0
        assert report.embedded == 1
        assert report.updated == 0

    def test_bulk_failures_are_reported_and_not_counted_as_updates(self) -> None:
        client = _FakeClient(
            [_hit("doc_1", "text"), _hit("doc_2", "text")],
            bulk_failures=["doc_2: rejected"],
        )
        report = _run(client, _FakeEncoder())
        assert report.updated == 1
        assert report.failed == ["doc_2: rejected"]

    def test_limit_is_honoured(self) -> None:
        client = _FakeClient([_hit(f"doc_{i}", "text") for i in range(10)])
        report = _run(client, _FakeEncoder(), limit=3)
        assert report.scanned == 3


class TestReport:
    def test_report_serialises_to_operator_readable_keys(self) -> None:
        report = BackfillReport(scanned=2, embedded=1, updated=1, elapsed_seconds=1.234)
        payload = report.as_dict()
        assert payload["scanned"] == 2
        assert payload["elapsed_seconds"] == 1.23
        assert payload["skipped_no_content"] == []
