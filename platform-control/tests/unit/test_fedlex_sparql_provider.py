from __future__ import annotations

from types import SimpleNamespace

import httpx
import pytest

from platform_control.services.fedlex_sparql_provider import FedlexSparqlProvider


class FakeAsyncClient:
    def __init__(self, *args, **kwargs) -> None:
        del args, kwargs

    async def __aenter__(self) -> FakeAsyncClient:
        return self

    async def __aexit__(self, exc_type, exc, tb) -> None:
        del exc_type, exc, tb

    async def get(self, url: str, *, params=None, headers=None):
        del headers
        query = (params or {}).get("query", "")
        request = httpx.Request("GET", url, params=params)
        if (
            url
            == "https://www.fedlex.admin.ch/filestore/fedlex.data.admin.ch/eli/cc/1999/404/20240303/de/html/fedlex-data-admin-ch-eli-cc-1999-404-20240303-de-html.html"
        ):
            return httpx.Response(
                200,
                text=(
                    "<html><body><h1>Bundesverfassung der Schweizerischen Eidgenossenschaft</h1>"
                    "<article><h2>Art. 1</h2><p>Das Schweizervolk und die Kantone ...</p></article>"
                    "</body></html>"
                ),
                headers={"content-type": "text/html; charset=utf-8"},
                request=request,
            )
        if "SELECT ?member" in query:
            return httpx.Response(
                200,
                json={
                    "results": {
                        "bindings": [
                            {
                                "member": {
                                    "type": "uri",
                                    "value": "https://fedlex.data.admin.ch/eli/cc/1999/404/20240101",
                                }
                            },
                            {
                                "member": {
                                    "type": "uri",
                                    "value": "https://fedlex.data.admin.ch/eli/cc/1999/404/20240303",
                                }
                            },
                        ]
                    }
                },
                request=request,
            )
        if "SELECT ?expr" in query:
            return httpx.Response(
                200,
                json={
                    "results": {
                        "bindings": [
                            {
                                "expr": {
                                    "type": "uri",
                                    "value": "https://fedlex.data.admin.ch/eli/cc/1999/404/20240303/de",
                                }
                            },
                            {
                                "expr": {
                                    "type": "uri",
                                    "value": "https://fedlex.data.admin.ch/eli/cc/1999/404/20240303/fr",
                                }
                            },
                        ]
                    }
                },
                request=request,
            )
        if "SELECT ?title ?titleShort" in query:
            return httpx.Response(
                200,
                json={
                    "results": {
                        "bindings": [
                            {
                                "title": {"type": "literal", "value": "Bundesverfassung"},
                                "titleShort": {"type": "literal", "value": "BV"},
                            }
                        ]
                    }
                },
                request=request,
            )
        if "DESCRIBE" in query:
            return httpx.Response(
                200,
                text=(
                    "<https://fedlex.data.admin.ch/eli/cc/1999/404/20240303/de> "
                    "<http://data.legilux.public.lu/resource/ontology/jolux#title> "
                    '"Bundesverfassung" .'
                ),
                headers={"content-type": "text/turtle; charset=utf-8"},
                request=request,
            )
        raise AssertionError(f"Unexpected query: {query}")


@pytest.mark.asyncio
async def test_minimal_work_to_expression_flow_extracts_expression_uris(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    monkeypatch.setattr(httpx, "AsyncClient", FakeAsyncClient)
    provider = FedlexSparqlProvider()
    source_version = SimpleNamespace(
        acquisition_spec={
            "seed_url": "https://fedlex.data.admin.ch/eli/cc/1999/404",
            "sparql_endpoint": "https://fedlex.data.admin.ch/sparqlendpoint",
            "preferred_languages": ["de"],
            "max_expressions": 1,
        }
    )

    result = await provider.start_run(
        SimpleNamespace(),
        source_version,
        SimpleNamespace(run_id="run_123"),
    )

    assert result.provider == "fedlex_sparql"
    assert result.request_payload["work_uris"] == ["https://fedlex.data.admin.ch/eli/cc/1999/404"]
    assert result.request_payload["preferred_languages"] == ["de"]
    assert result.request_payload["manifestation_format"] == "html"
    assert result.response_payload["captured"] == 1
    assert result.response_payload["failed"] == 0
    assert len(result.inline_resources) == 1
    payload = result.inline_resources[0]
    assert payload.source_url == "https://fedlex.data.admin.ch/eli/cc/1999/404"
    assert payload.final_url == (
        "https://www.fedlex.admin.ch/filestore/fedlex.data.admin.ch/"
        "eli/cc/1999/404/20240303/de/html/"
        "fedlex-data-admin-ch-eli-cc-1999-404-20240303-de-html.html"
    )
    assert payload.content_type == "text/html"
    assert "<article>" in payload.body
    assert "Art. 1" in payload.body
    assert "Bundesverfassung" in payload.body
    assert (
        payload.metadata["concrete_work_uri"]
        == "https://fedlex.data.admin.ch/eli/cc/1999/404/20240303"
    )
    assert payload.metadata["expression_uris"] == [
        "https://fedlex.data.admin.ch/eli/cc/1999/404/20240303/de"
    ]
    assert payload.metadata["title"] == "Bundesverfassung"
    assert payload.metadata["title_short"] == "BV"
    # ELI URI emission (T5.1): prefer the abstract seed work URI, not the
    # dated concrete form, so canonical output matches the ELI shape that
    # external ELI consumers expect.
    assert payload.metadata["eli_uri"] == "https://fedlex.data.admin.ch/eli/cc/1999/404"


def test_eli_uri_for_work_prefers_abstract_seed():
    provider = FedlexSparqlProvider()
    uri = provider._eli_uri_for_work(
        "https://fedlex.data.admin.ch/eli/cc/1999/404",
        "https://fedlex.data.admin.ch/eli/cc/1999/404/20240303",
    )
    assert uri == "https://fedlex.data.admin.ch/eli/cc/1999/404"


def test_eli_uri_for_work_falls_back_to_concrete():
    provider = FedlexSparqlProvider()
    uri = provider._eli_uri_for_work(
        "https://example.test/not-eli",
        "https://fedlex.data.admin.ch/eli/cc/1999/404/20240303",
    )
    assert uri == "https://fedlex.data.admin.ch/eli/cc/1999/404/20240303"


def test_eli_uri_for_work_returns_none_without_fedlex_eli():
    provider = FedlexSparqlProvider()
    assert provider._eli_uri_for_work("https://other.example/foo", "https://other/bar") is None


# ─── Cantonal discovery helpers (T4.4) ─────────────────────────────────────
# These helpers are not yet wired into start_run(); exercised here so the
# query shape and IRI mapping are tested ahead of the live acceptance run.


def test_canton_iri_from_iso_3166_2_code():
    provider = FedlexSparqlProvider()
    assert provider._canton_iri("CH-ZH") == "https://fedlex.data.admin.ch/vocabulary/canton/ZH"


def test_canton_iri_accepts_bare_two_letter_code():
    provider = FedlexSparqlProvider()
    assert provider._canton_iri("VS") == "https://fedlex.data.admin.ch/vocabulary/canton/VS"


def test_canton_iri_rejects_garbage():
    provider = FedlexSparqlProvider()
    import pytest

    with pytest.raises(ValueError, match="Invalid ISO 3166-2:CH"):
        provider._canton_iri("CH-XYZ")
    with pytest.raises(ValueError, match="Invalid ISO 3166-2:CH"):
        provider._canton_iri("")


def test_build_canton_discovery_query_shape():
    provider = FedlexSparqlProvider()
    query = provider._build_canton_discovery_query("CH-ZH", limit=25)
    assert "jolux:CantonOfOrigin" in query
    assert "<https://fedlex.data.admin.ch/vocabulary/canton/ZH>" in query
    assert "LIMIT 25" in query
    assert "SELECT ?work" in query


def test_build_canton_discovery_query_default_limit():
    provider = FedlexSparqlProvider()
    query = provider._build_canton_discovery_query("CH-VS")
    assert "LIMIT 50" in query
