"""Unit tests for EurLexSparqlProvider.

WHY THESE TESTS EXIST:
- The EUR-Lex SPARQL adapter implements the work → expression →
  manifestation flow against the CDM ontology. Mocking the endpoint
  verifies the query shapes, language selection, CELEX capture, and
  ProviderResource emission without requiring network.
- The first live smoke run (GDPR CELEX 32016R0679) flips templates
  `enabled: true` — these tests guard the code path that acceptance
  run will exercise.
"""

from __future__ import annotations

from types import SimpleNamespace

import httpx
import pytest

from platform_control.errors import ProviderConfigurationError
from platform_control.services.eur_lex_sparql_provider import EurLexSparqlProvider


class FakeAsyncClient:
    def __init__(self, *args, **kwargs) -> None:
        del args, kwargs

    async def __aenter__(self) -> FakeAsyncClient:
        return self

    async def __aexit__(self, exc_type, exc, tb) -> None:
        del exc_type, exc, tb

    async def get(self, url: str, *, params=None, headers=None):
        del headers
        params = params or {}
        query = params.get("query", "")
        request = httpx.Request("GET", url, params=params)

        # Cellar manifestation fetch
        if url.startswith("http://publications.europa.eu/resource/cellar/") and url.endswith(
            ".html"
        ):
            return httpx.Response(
                200,
                text=(
                    "<html><body>"
                    "<h1>REGULATION (EU) 2016/679 OF THE EUROPEAN PARLIAMENT"
                    " AND OF THE COUNCIL</h1>"
                    "<p>on the protection of natural persons with regard to"
                    " the processing of personal data...</p>"
                    "</body></html>"
                ),
                headers={"content-type": "text/html; charset=utf-8"},
                request=request,
            )

        if "cdm:work_has_expression" in query:
            return httpx.Response(
                200,
                json={
                    "results": {
                        "bindings": [
                            {
                                "expression": {
                                    "type": "uri",
                                    "value": "http://data.europa.eu/eli/reg/2016/679/oj/eng",
                                },
                                "language": {
                                    "type": "uri",
                                    "value": "http://publications.europa.eu/resource/authority/language/ENG",
                                },
                                "celex": {
                                    "type": "literal",
                                    "value": "32016R0679",
                                },
                            },
                            {
                                "expression": {
                                    "type": "uri",
                                    "value": "http://data.europa.eu/eli/reg/2016/679/oj/deu",
                                },
                                "language": {
                                    "type": "uri",
                                    "value": "http://publications.europa.eu/resource/authority/language/DEU",
                                },
                                "celex": {
                                    "type": "literal",
                                    "value": "32016R0679",
                                },
                            },
                        ]
                    }
                },
                request=request,
            )
        if "cdm:expression_manifested_by_manifestation" in query:
            return httpx.Response(
                200,
                json={
                    "results": {
                        "bindings": [
                            {
                                "manifestation": {
                                    "type": "uri",
                                    "value": "http://publications.europa.eu/resource/cellar/gdpr-eng.html",
                                },
                                "format": {
                                    "type": "uri",
                                    "value": "http://publications.europa.eu/resource/authority/file-type/HTML",
                                },
                            },
                            {
                                "manifestation": {
                                    "type": "uri",
                                    "value": "http://publications.europa.eu/resource/cellar/gdpr-eng.pdf",
                                },
                                "format": {
                                    "type": "uri",
                                    "value": "http://publications.europa.eu/resource/authority/file-type/PDF",
                                },
                            },
                        ]
                    }
                },
                request=request,
            )
        if "cdm:expression_title" in query:
            return httpx.Response(
                200,
                json={
                    "results": {
                        "bindings": [
                            {
                                "title": {
                                    "type": "literal",
                                    "value": (
                                        "Regulation (EU) 2016/679"
                                        " (General Data Protection Regulation)"
                                    ),
                                }
                            }
                        ]
                    }
                },
                request=request,
            )
        raise AssertionError(f"Unexpected request url={url!r} query={query!r}")


@pytest.mark.asyncio
async def test_gdpr_end_to_end_flow_emits_eli_uri_and_celex(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    monkeypatch.setattr(httpx, "AsyncClient", FakeAsyncClient)
    provider = EurLexSparqlProvider()
    source_version = SimpleNamespace(
        acquisition_spec={
            "seed_url": "http://data.europa.eu/eli/reg/2016/679/oj",
            "preferred_languages": ["en"],
            "max_expressions": 1,
        }
    )
    result = await provider.start_run(
        SimpleNamespace(),
        source_version,
        SimpleNamespace(run_id="run_eu_123"),
    )

    assert result.provider == "eur_lex_sparql"
    assert result.request_payload["work_uris"] == ["http://data.europa.eu/eli/reg/2016/679/oj"]
    assert result.request_payload["preferred_languages"] == ["en"]
    assert result.response_payload["captured"] == 1
    assert result.response_payload["failed"] == 0

    assert len(result.inline_resources) == 1
    payload = result.inline_resources[0]
    assert payload.source_url == "http://data.europa.eu/eli/reg/2016/679/oj"
    assert payload.final_url == ("http://publications.europa.eu/resource/cellar/gdpr-eng.html")
    assert payload.content_type == "text/html"
    assert "REGULATION (EU) 2016/679" in payload.body
    assert payload.metadata["eli_uri"] == "http://data.europa.eu/eli/reg/2016/679/oj"
    assert payload.metadata["celex"] == "32016R0679"
    assert payload.metadata["language"] == "en"
    assert payload.metadata["expression_uri"] == "http://data.europa.eu/eli/reg/2016/679/oj/eng"


@pytest.mark.asyncio
async def test_language_preference_ranking_picks_german_when_listed_first(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    monkeypatch.setattr(httpx, "AsyncClient", FakeAsyncClient)
    provider = EurLexSparqlProvider()
    source_version = SimpleNamespace(
        acquisition_spec={
            "seed_url": "http://data.europa.eu/eli/reg/2016/679/oj",
            "preferred_languages": ["de", "en"],
            "max_expressions": 1,
        }
    )
    result = await provider.start_run(
        SimpleNamespace(),
        source_version,
        SimpleNamespace(run_id="run_eu_124"),
    )
    assert len(result.inline_resources) == 1
    payload = result.inline_resources[0]
    assert payload.metadata["expression_uri"] == "http://data.europa.eu/eli/reg/2016/679/oj/deu"
    assert payload.metadata["language"] == "de"


# ─── Helper-level unit tests ─────────────────────────────────


def test_language_iri_for_iso_known_code():
    provider = EurLexSparqlProvider()
    assert (
        provider._language_iri_for_iso("en")
        == "http://publications.europa.eu/resource/authority/language/ENG"
    )
    assert (
        provider._language_iri_for_iso("it")
        == "http://publications.europa.eu/resource/authority/language/ITA"
    )


def test_language_iri_for_iso_unknown_code_returns_none():
    provider = EurLexSparqlProvider()
    assert provider._language_iri_for_iso("xx") is None


def test_language_iri_to_iso_roundtrip():
    provider = EurLexSparqlProvider()
    iri = "http://publications.europa.eu/resource/authority/language/DEU"
    assert provider._language_iri_to_iso(iri) == "de"


def test_language_iri_to_iso_handles_non_authority_iri():
    provider = EurLexSparqlProvider()
    assert provider._language_iri_to_iso("http://example.test/not-a-lang") is None


def test_validate_eurlex_eli_rejects_non_eli_seed():
    provider = EurLexSparqlProvider()
    with pytest.raises(ProviderConfigurationError, match="ELI URI"):
        provider._validate_eurlex_eli("http://data.europa.eu/whatever/foo")


def test_validate_eurlex_eli_rejects_wrong_host():
    provider = EurLexSparqlProvider()
    with pytest.raises(ProviderConfigurationError, match="host"):
        provider._validate_eurlex_eli("http://example.test/eli/reg/2016/679/oj")


def test_validate_eurlex_url_accepts_sparql_endpoint():
    provider = EurLexSparqlProvider()
    assert (
        provider._validate_eurlex_url("http://publications.europa.eu/webapi/rdf/sparql")
        == "http://publications.europa.eu/webapi/rdf/sparql"
    )


def test_seed_work_uris_requires_some_input():
    provider = EurLexSparqlProvider()
    with pytest.raises(ProviderConfigurationError, match="seed_url"):
        provider._seed_work_uris({})


def test_seed_work_uris_accepts_seed_urls_list():
    provider = EurLexSparqlProvider()
    uris = provider._seed_work_uris(
        {
            "seed_urls": [
                "http://data.europa.eu/eli/reg/2016/679/oj",
                "http://data.europa.eu/eli/dir/2019/790/oj",
            ]
        }
    )
    assert len(uris) == 2


def test_looks_like_eli():
    assert EurLexSparqlProvider._looks_like_eli("http://data.europa.eu/eli/reg/2016/679/oj")
    assert not EurLexSparqlProvider._looks_like_eli(
        "http://publications.europa.eu/resource/cellar/foo.html"
    )
    assert not EurLexSparqlProvider._looks_like_eli("not a url")


def test_preferred_languages_defaults_to_english():
    provider = EurLexSparqlProvider()
    assert provider._preferred_languages(None) == ["en"]
    assert provider._preferred_languages({}) == ["en"]


def test_preferred_languages_normalizes_case_and_whitespace():
    provider = EurLexSparqlProvider()
    assert provider._preferred_languages({"preferred_languages": ["EN", " de ", "FR"]}) == [
        "en",
        "de",
        "fr",
    ]
