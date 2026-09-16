"""Query-side sparse encoding (ADR-0054) — the endpoint the search path will call.

No model is loaded here. Everything that decides what lands on the wire — truncation,
which mass is reported, how an absent encoder is answered — is a pure function around
the model, and is tested without it. A test that needs a 2.3GB download is a test that
does not run.
"""

from __future__ import annotations

import pytest
from fastapi.testclient import TestClient

from document_intelligence.embeddings import query_encoding
from document_intelligence.embeddings.query_encoding import (
    QueryEncoderUnavailable,
    encode_query,
)
from document_intelligence.service.app import create_app


class _FakeEncoder:
    """Stands in for SparseEncoder. `model_name` is read by the caching helper."""

    def __init__(self, vector: dict[str, float], model_name: str = "BAAI/bge-m3") -> None:
        self._vector = vector
        self.model_name = model_name
        self.calls: list[str] = []

    def encode_query(self, text: str) -> dict[str, float]:
        self.calls.append(text)
        return dict(self._vector)


class _MissingExtraEncoder:
    model_name = "BAAI/bge-m3"

    def encode_query(self, text: str) -> dict[str, float]:
        del text
        raise RuntimeError("The `embeddings` extra is not installed. Install with: uv sync --extra embeddings")


@pytest.fixture(autouse=True)
def _reset_encoder_singleton():
    query_encoding._encoder = None
    yield
    query_encoding._encoder = None


def _install(monkeypatch: pytest.MonkeyPatch, encoder) -> None:
    monkeypatch.setattr(query_encoding, "_get_encoder", lambda model: encoder)


def test_encode_query_returns_features_and_mass(monkeypatch: pytest.MonkeyPatch) -> None:
    _install(monkeypatch, _FakeEncoder({"t1": 0.5, "t2": 0.25}))

    result = encode_query("Hund Leine")

    assert result.features == {"t1": 0.5, "t2": 0.25}
    assert result.weight_mass == pytest.approx(0.75)
    assert result.truncated is False
    assert result.features_before_truncation == 2


def test_truncation_reports_the_mass_of_the_vector_actually_sent(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    """The D4 coverage ratio divides by this. Reporting the untruncated mass would
    describe a query that was never issued — and would understate coverage, so a real
    hit could be refused."""
    _install(monkeypatch, _FakeEncoder({"t1": 0.5, "t2": 0.3, "t3": 0.2}))

    result = encode_query("x", max_features=2)

    assert result.features == {"t1": 0.5, "t2": 0.3}, "must keep the HIGHEST-weighted features"
    assert result.weight_mass == pytest.approx(0.8), "mass must exclude the dropped feature"
    assert result.truncated is True
    assert result.features_before_truncation == 3


def test_missing_extra_is_a_named_unavailability_not_a_crash(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    _install(monkeypatch, _MissingExtraEncoder())

    with pytest.raises(QueryEncoderUnavailable) as excinfo:
        encode_query("Hund")

    assert excinfo.value.reason == "embeddings_extra_not_installed"


def test_empty_query_is_rejected(monkeypatch: pytest.MonkeyPatch) -> None:
    _install(monkeypatch, _FakeEncoder({"t1": 1.0}))
    with pytest.raises(ValueError):
        encode_query("   ")


def test_endpoint_encodes(monkeypatch: pytest.MonkeyPatch) -> None:
    _install(monkeypatch, _FakeEncoder({"t1": 0.5, "t2": 0.25}))
    client = TestClient(create_app())

    response = client.post("/v1/embeddings/query-sparse", json={"query": "Hund Leine"})

    assert response.status_code == 200
    body = response.json()
    assert body["features"] == {"t1": 0.5, "t2": 0.25}
    assert body["feature_count"] == 2
    assert body["weight_mass"] == pytest.approx(0.75)
    assert body["truncated"] is False


def test_endpoint_answers_503_with_a_reason_when_the_image_has_no_encoder(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    """503 and not 500: 'no model in this image' and 'this query is unanswerable' are
    different facts, and a search path that cannot tell them apart is #958 at a service
    boundary. Delete the QueryEncoderUnavailable handler and this goes red."""
    _install(monkeypatch, _MissingExtraEncoder())
    client = TestClient(create_app(), raise_server_exceptions=False)

    response = client.post("/v1/embeddings/query-sparse", json={"query": "Hund"})

    assert response.status_code == 503
    assert response.json()["detail"]["reason"] == "embeddings_extra_not_installed"


def test_endpoint_rejects_an_empty_query_before_loading_anything() -> None:
    client = TestClient(create_app())
    response = client.post("/v1/embeddings/query-sparse", json={"query": ""})
    assert response.status_code == 422


def test_endpoint_bounds_max_features() -> None:
    client = TestClient(create_app())
    response = client.post("/v1/embeddings/query-sparse", json={"query": "x", "max_features": 999_999})
    assert response.status_code == 422
