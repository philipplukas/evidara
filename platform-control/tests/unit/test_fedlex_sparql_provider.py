from __future__ import annotations

from datetime import date
from types import SimpleNamespace

import httpx
import pytest

from platform_control.services.fedlex_sparql_provider import (
    FedlexSparqlProvider,
    _ConsolidationMember,
)


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


# ─── In-force consolidation selection (#633) ────────────────────────────────
# The provider must acquire the consolidation *in force* at the requested date,
# never the newest one — the bug acquired "Stand am 1. Januar 2029".

_BV_PAST = _ConsolidationMember(
    uri="https://fedlex.data.admin.ch/eli/cc/1999/404/20220213",
    in_force_from=date(2022, 2, 13),
    in_force_until=date(2023, 12, 31),
)
_BV_CURRENT = _ConsolidationMember(
    uri="https://fedlex.data.admin.ch/eli/cc/1999/404/20240303",
    in_force_from=date(2024, 3, 3),
    in_force_until=date(2028, 12, 31),
)
_BV_FUTURE = _ConsolidationMember(
    uri="https://fedlex.data.admin.ch/eli/cc/1999/404/20290101",
    in_force_from=date(2029, 1, 1),
    in_force_until=None,
)


def test_select_member_picks_in_force_today_not_newest_future():
    provider = FedlexSparqlProvider()
    selected, in_force = provider._select_consolidation_member(
        members=[_BV_PAST, _BV_CURRENT, _BV_FUTURE],
        as_of=date(2026, 7, 17),
    )
    assert selected == _BV_CURRENT
    assert in_force is True


def test_select_member_explicit_future_as_of_selects_future_consolidation():
    provider = FedlexSparqlProvider()
    selected, in_force = provider._select_consolidation_member(
        members=[_BV_PAST, _BV_CURRENT, _BV_FUTURE],
        as_of=date(2029, 6, 1),
    )
    assert selected == _BV_FUTURE
    assert in_force is True


def test_select_member_between_windows_uses_last_effective_and_flags_expired():
    # Newest consolidation whose in_force_from has arrived, but its until has
    # passed and no successor is yet in force: still not a future one.
    provider = FedlexSparqlProvider()
    selected, in_force = provider._select_consolidation_member(
        members=[_BV_PAST, _BV_CURRENT, _BV_FUTURE],
        as_of=date(2023, 12, 31),
    )
    assert selected == _BV_PAST
    assert in_force is True


def test_select_member_before_any_consolidation_flags_not_in_force():
    provider = FedlexSparqlProvider()
    selected, in_force = provider._select_consolidation_member(
        members=[_BV_CURRENT, _BV_FUTURE],
        as_of=date(2000, 1, 1),
    )
    assert selected == _BV_CURRENT  # earliest available
    assert in_force is False


def test_select_member_without_dates_falls_back_to_newest_by_uri():
    provider = FedlexSparqlProvider()
    undated = [
        _ConsolidationMember(
            uri="https://fedlex.data.admin.ch/eli/cc/1999/404/20240101",
            in_force_from=None,
            in_force_until=None,
        ),
        _ConsolidationMember(
            uri="https://fedlex.data.admin.ch/eli/cc/1999/404/20240303",
            in_force_from=None,
            in_force_until=None,
        ),
    ]
    selected, in_force = provider._select_consolidation_member(
        members=undated,
        as_of=date(2026, 7, 17),
    )
    assert selected.uri.endswith("/20240303")
    assert in_force is True


def test_as_of_date_defaults_to_today():
    provider = FedlexSparqlProvider()
    assert provider._as_of_date({}) == date.today()


def test_as_of_date_reads_explicit_iso():
    provider = FedlexSparqlProvider()
    assert provider._as_of_date({"as_of_date": "2029-01-01"}) == date(2029, 1, 1)


def test_as_of_date_rejects_garbage():
    from platform_control.errors import ProviderConfigurationError

    provider = FedlexSparqlProvider()
    with pytest.raises(ProviderConfigurationError, match="as_of_date must be ISO"):
        provider._as_of_date({"as_of_date": "1 Jan 2029"})


class DatedMemberAsyncClient(FakeAsyncClient):
    """Serves consolidation members carrying jolux applicability dates.

    Includes a future consolidation (`20290101`, in force 2029-01-01) so the
    selector is exercised against the exact shape of the #633 bug. Everything
    else (expression, title, filestore HTML for `20240303`) is served by the
    base fake, so the default-today run must resolve to `20240303`.
    """

    async def get(self, url: str, *, params=None, headers=None):
        query = (params or {}).get("query", "")
        if "SELECT ?member" in query:
            request = httpx.Request("GET", url, params=params)

            def member(uri: str, dfrom: str, dto: str | None) -> dict:
                row: dict = {"member": {"type": "uri", "value": uri}}
                row["inForceFrom"] = {
                    "type": "typed-literal",
                    "datatype": "http://www.w3.org/2001/XMLSchema#date",
                    "value": dfrom,
                }
                if dto is not None:
                    row["inForceUntil"] = {
                        "type": "typed-literal",
                        "datatype": "http://www.w3.org/2001/XMLSchema#date",
                        "value": dto,
                    }
                return row

            return httpx.Response(
                200,
                json={
                    "results": {
                        "bindings": [
                            member(
                                "https://fedlex.data.admin.ch/eli/cc/1999/404/20220213",
                                "2022-02-13",
                                "2023-12-31",
                            ),
                            member(
                                "https://fedlex.data.admin.ch/eli/cc/1999/404/20240303",
                                "2024-03-03",
                                "2028-12-31",
                            ),
                            member(
                                "https://fedlex.data.admin.ch/eli/cc/1999/404/20290101",
                                "2029-01-01",
                                None,
                            ),
                        ]
                    }
                },
                request=request,
            )
        return await super().get(url, params=params, headers=headers)


@pytest.mark.asyncio
async def test_start_run_selects_in_force_and_emits_validity_dates(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    monkeypatch.setattr(httpx, "AsyncClient", DatedMemberAsyncClient)
    provider = FedlexSparqlProvider()
    source_version = SimpleNamespace(
        acquisition_spec={
            "seed_url": "https://fedlex.data.admin.ch/eli/cc/1999/404",
            "sparql_endpoint": "https://fedlex.data.admin.ch/sparqlendpoint",
            "preferred_languages": ["de"],
            "max_expressions": 1,
            # No as_of_date → defaults to today, which must skip the 2029 member.
        }
    )

    result = await provider.start_run(
        SimpleNamespace(),
        source_version,
        SimpleNamespace(run_id="run_in_force"),
    )

    assert result.response_payload["captured"] == 1
    metadata = result.inline_resources[0].metadata
    # Selected the consolidation in force today, NOT the 2029 one.
    assert metadata["concrete_work_uri"] == (
        "https://fedlex.data.admin.ch/eli/cc/1999/404/20240303"
    )
    assert metadata["in_force_from"] == "2024-03-03"
    assert metadata["in_force_until"] == "2028-12-31"
    assert metadata["in_force_at_selection"] is True
    assert metadata["selected_as_of"] == date.today().isoformat()
    assert result.request_payload["as_of_date"] == date.today().isoformat()


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


class CantonDiscoveryAsyncClient(FakeAsyncClient):
    """Extends the federal fake with a cantonal-discovery response.

    The `jolux:CantonOfOrigin` query resolves to the BV work URI so the
    discovered work flows through the same member→expression→manifestation
    pipeline the base fake already serves.
    """

    async def get(self, url: str, *, params=None, headers=None):
        query = (params or {}).get("query", "")
        if "SELECT ?work" in query and "jolux:CantonOfOrigin" in query:
            request = httpx.Request("GET", url, params=params)
            return httpx.Response(
                200,
                json={
                    "results": {
                        "bindings": [
                            {
                                "work": {
                                    "type": "uri",
                                    "value": "https://fedlex.data.admin.ch/eli/cc/1999/404",
                                }
                            }
                        ]
                    }
                },
                request=request,
            )
        return await super().get(url, params=params, headers=headers)


@pytest.mark.asyncio
async def test_canton_scope_discovers_and_processes_works(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    monkeypatch.setattr(httpx, "AsyncClient", CantonDiscoveryAsyncClient)
    provider = FedlexSparqlProvider()
    source_version = SimpleNamespace(
        acquisition_spec={
            "scope_kind": "canton",
            "canton": "CH-ZH",
            "sparql_endpoint": "https://fedlex.data.admin.ch/sparqlendpoint",
            "preferred_languages": ["de"],
            "max_expressions": 1,
            "max_works": 10,
        }
    )

    result = await provider.start_run(
        SimpleNamespace(),
        source_version,
        SimpleNamespace(run_id="run_canton_zh"),
    )

    assert result.response_payload["scope_kind"] == "canton"
    assert result.response_payload["canton"] == "CH-ZH"
    assert result.response_payload["captured"] == 1
    assert result.request_payload["work_uris"] == ["https://fedlex.data.admin.ch/eli/cc/1999/404"]
    assert result.inline_resources[0].content_type == "text/html"
    assert result.inline_failure_reason is None


@pytest.mark.asyncio
async def test_canton_scope_without_canton_code_fails_cleanly(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    monkeypatch.setattr(httpx, "AsyncClient", CantonDiscoveryAsyncClient)
    provider = FedlexSparqlProvider()
    source_version = SimpleNamespace(
        acquisition_spec={
            "scope_kind": "canton",
            "sparql_endpoint": "https://fedlex.data.admin.ch/sparqlendpoint",
        }
    )

    result = await provider.start_run(
        SimpleNamespace(),
        source_version,
        SimpleNamespace(run_id="run_canton_missing"),
    )

    assert result.response_payload["captured"] == 0
    assert result.response_payload["failed"] == 1
    assert "requires acquisition_spec.canton" in result.response_payload["failures"][0]["error"]
    assert "did not capture any resources" in (result.inline_failure_reason or "")


def test_plan_canton_mode_needs_no_seed_urls() -> None:
    provider = FedlexSparqlProvider()
    plan = provider.plan(
        SimpleNamespace(),
        SimpleNamespace(acquisition_spec={"scope_kind": "canton", "canton": "CH-BE"}),
    )
    assert plan.mode == "canton_discovery"
    assert plan.seed_urls == []
    assert any("canton=CH-BE" in note for note in plan.notes)
