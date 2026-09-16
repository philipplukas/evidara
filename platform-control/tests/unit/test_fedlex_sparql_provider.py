from __future__ import annotations

from datetime import date, timedelta
from types import SimpleNamespace

import httpx
import pytest

from acquisition_core.identity import upstream_locator
from acquisition_core.normalization import ArtifactPipeline
from platform_control.errors import ProviderConfigurationError
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
                # Three articles, not one. The single-`Art.` fixture this replaced
                # scored below `content_gate`'s marker floor of three, so it was
                # indistinguishable from a filestore error page — which is what the
                # density gate is for. Real Fedlex HTML clears the floor in its first
                # screenful; `scripts/ch-fedlex-fast-loop.sh` has asserted exactly
                # this (`art_density >= 3`) against the live endpoint all along.
                text=(
                    "<html><body><h1>Bundesverfassung der Schweizerischen Eidgenossenschaft</h1>"
                    "<article><h2>Art. 1</h2><p>Das Schweizervolk und die Kantone ...</p></article>"
                    "<article><h2>Art. 2 Abs. 1</h2><p>Die Schweizerische Eidgenossenschaft "
                    "schützt die Freiheit ...</p></article>"
                    "<article><h2>Art. 3</h2><p>Die Kantone sind souverän ...</p></article>"
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
        if "SELECT ?status ?entryIntoForce" in query:
            # The BV is in force (enforcement-status/0) since 2000-01-01.
            return httpx.Response(
                200,
                json={
                    "results": {
                        "bindings": [
                            {
                                "status": {
                                    "type": "uri",
                                    "value": (
                                        "https://fedlex.data.admin.ch/vocabulary/"
                                        "enforcement-status/0"
                                    ),
                                },
                                "entryIntoForce": {"type": "literal", "value": "2000-01-01"},
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


def test_the_fedlex_end_date_is_the_inclusive_last_day_in_force():
    """The boundary, measured — and the same one the consumer uses (#843).

    `jolux:dateEndApplicability` is INCLUSIVE, so it is emitted as
    `in_force_until` unconverted. Measured live 2026-09-03: one SPARQL query
    pulled 3000 consolidation members across 1193 works carrying both dates, and
    every consecutive pair within a work was compared. **1800 of 1806 adjacent
    pairs have successor start = predecessor end + 1 day, and ZERO pairs are
    equal.** An exclusive end-date would produce equal dates; that case does not
    occur. (The six outliers are 13-8767 day gaps — missing consolidations, not a
    second convention.)

    The members below are a real adjacent pair from that sample,
    `eli/cc/1/1_1_1`, which is why the dates look nothing like the `_BV_*`
    fixtures above: those have a deliberate gap and cannot express adjacency.

    The assertion that matters is the last one. `_select_consolidation_member`
    reads the end date inclusively (`in_force_until >= as_of`), and so does
    `resolveInForceState` in legal-search
    (`in-force.ts:60-61` repeals only on `asOf > until`). On 1885-12-21 the
    earlier consolidation is selected and reported in force; on 1885-12-22 the
    successor takes over. Neither day is claimed twice and none falls between.
    """
    earlier = _ConsolidationMember(
        uri="https://fedlex.data.admin.ch/eli/cc/1/1_1_1/18790401",
        in_force_from=date(1879, 4, 1),
        in_force_until=date(1885, 12, 21),
    )
    later = _ConsolidationMember(
        uri="https://fedlex.data.admin.ch/eli/cc/1/1_1_1/18851222",
        in_force_from=date(1885, 12, 22),
        in_force_until=date(1887, 12, 19),
    )
    assert later.in_force_from - earlier.in_force_until == timedelta(days=1)

    provider = FedlexSparqlProvider()

    selected, in_force = provider._select_consolidation_member(
        members=[earlier, later], as_of=date(1885, 12, 21)
    )
    assert (selected, in_force) == (earlier, True)

    selected, in_force = provider._select_consolidation_member(
        members=[earlier, later], as_of=date(1885, 12, 22)
    )
    assert (selected, in_force) == (later, True)


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
    # Act-level signals (#628): status from the enforcement-status vocabulary,
    # and the act's ORIGINAL entry into force — which is not the selected
    # consolidation's start date.
    assert metadata["in_force_status"] == "in_force"
    assert metadata["entry_into_force"] == "2000-01-01"


class RepealedWorkAsyncClient(DatedMemberAsyncClient):
    """A repealed act whose newest consolidation is open-ended.

    Measured live (2026-07-19): 3 works with `enforcement-status/3` have a
    newest consolidation carrying no `dateEndApplicability`. Consolidation
    dates alone therefore say "still in force" for repealed law — the act-level
    status is the only signal that catches it.
    """

    async def get(self, url: str, *, params=None, headers=None):
        query = (params or {}).get("query", "")
        if "SELECT ?status ?entryIntoForce" in query:
            request = httpx.Request("GET", url, params=params)
            return httpx.Response(
                200,
                json={
                    "results": {
                        "bindings": [
                            {
                                "status": {
                                    "type": "uri",
                                    "value": (
                                        "https://fedlex.data.admin.ch/vocabulary/"
                                        "enforcement-status/3"
                                    ),
                                }
                            }
                        ]
                    }
                },
                request=request,
            )
        return await super().get(url, params=params, headers=headers)


@pytest.mark.asyncio
async def test_repealed_act_is_not_reported_in_force_despite_open_ended_consolidation(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    monkeypatch.setattr(httpx, "AsyncClient", RepealedWorkAsyncClient)
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
        SimpleNamespace(run_id="run_repealed"),
    )

    metadata = result.inline_resources[0].metadata
    assert metadata["in_force_status"] == "no_longer_in_force"
    # The consolidation window still reports its own end date, but the act-level
    # repeal overrides the in-force verdict so the canary fails closed.
    assert metadata["in_force_at_selection"] is False


class UnknownStatusAsyncClient(DatedMemberAsyncClient):
    """Fedlex publishes an enforcement-status code we do not recognise."""

    async def get(self, url: str, *, params=None, headers=None):
        query = (params or {}).get("query", "")
        if "SELECT ?status ?entryIntoForce" in query:
            request = httpx.Request("GET", url, params=params)
            return httpx.Response(
                200,
                json={
                    "results": {
                        "bindings": [
                            {
                                "status": {
                                    "type": "uri",
                                    "value": (
                                        "https://fedlex.data.admin.ch/vocabulary/"
                                        "enforcement-status/99"
                                    ),
                                }
                            }
                        ]
                    }
                },
                request=request,
            )
        return await super().get(url, params=params, headers=headers)


@pytest.mark.asyncio
async def test_unrecognised_enforcement_status_is_reported_as_none_not_guessed(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    monkeypatch.setattr(httpx, "AsyncClient", UnknownStatusAsyncClient)
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
        SimpleNamespace(run_id="run_unknown_status"),
    )

    metadata = result.inline_resources[0].metadata
    # An unknown vocabulary code must not be mapped onto a plausible value, and
    # must not silently flip the consolidation's in-force verdict.
    assert metadata["in_force_status"] is None
    assert metadata["in_force_at_selection"] is True


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


# ─── Cantonal discovery is removed, not dormant (#716) ─────────────────────
# `jolux:CantonOfOrigin` never existed and Fedlex publishes no cantonal law
# (measured — see the SCOPE note in the provider module). These tests pin the
# removal so a canton spec fails loudly instead of silently running a query
# that can only ever return zero bindings.


def test_canton_scope_spec_is_rejected() -> None:
    """`scope_kind`/`canton` are gone from the spec, and `extra="forbid"` refuses them."""
    from pydantic import ValidationError

    from platform_control.schemas.source import AcquisitionSpecAdapter

    with pytest.raises(ValidationError):
        AcquisitionSpecAdapter.validate_python(
            {
                "provider": "fedlex_sparql",
                "scope_kind": "canton",
                "canton": "CH-ZH",
            }
        )


def test_provider_exposes_no_canton_discovery_surface() -> None:
    provider = FedlexSparqlProvider()
    for removed in (
        "_is_canton_scope",
        "_canton_filter",
        "_canton_iri",
        "_build_canton_discovery_query",
        "_discover_works_by_canton",
        "_CANTON_WORK_DISCOVERY_QUERY",
        "_CANTON_IRI_BASE",
    ):
        assert not hasattr(provider, removed)


def test_plan_only_offers_the_federal_seed_mode() -> None:
    provider = FedlexSparqlProvider()
    plan = provider.plan(
        SimpleNamespace(),
        SimpleNamespace(
            acquisition_spec={"seed_urls": ["https://fedlex.data.admin.ch/eli/cc/1999/404"]}
        ),
    )
    assert plan.mode == "work_to_expression"
    assert plan.seed_urls == ["https://fedlex.data.admin.ch/eli/cc/1999/404"]


# ─── The legal-text density gate (#631/#635) ────────────────────
#
# `scripts/ch-fedlex-fast-loop.sh` has gated on `art_density >= 3` against this
# provider's output since it was written, and #635 lifted that heuristic into
# `acquisition_core.content_gate` so every provider could share it — but the sharing
# never reached the provider it came from. Until `start_run` called the gate, the
# check ran only in a canary script somebody has to remember to run.
#
# Mutation check: delete the `assess_legal_text_density(...)` block in
# `FedlexSparqlProvider.start_run` and `test_filestore_shell_is_refused...` fails —
# `captured` reads 1 and the shell is emitted as the Bundesverfassung.

_FILESTORE_URL = (
    "https://www.fedlex.admin.ch/filestore/fedlex.data.admin.ch/"
    "eli/cc/1999/404/20240303/de/html/"
    "fedlex-data-admin-ch-eli-cc-1999-404-20240303-de-html.html"
)


class ShellManifestationClient(FakeAsyncClient):
    """Serves a 200 carrying chrome where the filestore should carry the act."""

    async def get(self, url: str, *, params=None, headers=None):
        if url == _FILESTORE_URL:
            return httpx.Response(
                200,
                text=(
                    "<html><head><script>var app=1;</script></head><body>"
                    "<nav>Startseite Recht Bundesrecht Kontakt</nav>"
                    "<p>Die angeforderte Seite konnte nicht geladen werden.</p>"
                    "</body></html>"
                ),
                headers={"content-type": "text/html; charset=utf-8"},
                request=httpx.Request("GET", url),
            )
        return await super().get(url, params=params, headers=headers)


@pytest.mark.asyncio
async def test_filestore_shell_is_refused_rather_than_captured_as_the_act(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    monkeypatch.setattr(httpx, "AsyncClient", ShellManifestationClient)
    provider = FedlexSparqlProvider()
    result = await provider.start_run(
        SimpleNamespace(),
        SimpleNamespace(
            acquisition_spec={
                "seed_url": "https://fedlex.data.admin.ch/eli/cc/1999/404",
                "sparql_endpoint": "https://fedlex.data.admin.ch/sparqlendpoint",
                "preferred_languages": ["de"],
                "max_expressions": 1,
            }
        ),
        SimpleNamespace(run_id="run_shell"),
    )

    assert result.response_payload["captured"] == 0
    assert result.inline_resources == []
    assert result.response_payload["skipped"] == 1
    skipped = result.response_payload["skipped_documents"][0]
    assert skipped["reason"] == "no_legal_text_markers"
    assert skipped["legal_marker_count"] == 0
    # The SPARQL half succeeded, so the refusal must not read as "nothing found".
    assert "legal-text density gate" in result.inline_failure_reason


@pytest.mark.asyncio
async def test_a_genuine_act_passes_the_gate_and_carries_its_verdict(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    """The other half: the gate must not refuse honest law.

    Asserted on the same fixture the rest of this file uses, so a future edit that
    tightens the gate past what real Fedlex HTML carries fails here rather than in
    production.
    """
    monkeypatch.setattr(httpx, "AsyncClient", FakeAsyncClient)
    provider = FedlexSparqlProvider()
    result = await provider.start_run(
        SimpleNamespace(),
        SimpleNamespace(
            acquisition_spec={
                "seed_url": "https://fedlex.data.admin.ch/eli/cc/1999/404",
                "sparql_endpoint": "https://fedlex.data.admin.ch/sparqlendpoint",
                "preferred_languages": ["de"],
                "max_expressions": 1,
            }
        ),
        SimpleNamespace(run_id="run_ok"),
    )

    assert result.response_payload["captured"] == 1
    assert result.response_payload["skipped"] == 0
    metadata = result.inline_resources[0].metadata
    assert metadata["legal_text_assessment"] == "passed"
    assert metadata["legal_text_evidence"]["legal_marker_count"] >= 3


# --------------------------------------------------------------------------
# Document identity — one act, one document, across consolidations (#850)
# --------------------------------------------------------------------------


class AnyConsolidationAsyncClient(DatedMemberAsyncClient):
    """Serves the filestore HTML for *any* consolidation, not just 20240303.

    `FakeAsyncClient` hard-codes the 2024 manifestation URL, which is enough for the
    single-capture tests but cannot express "the same act, fetched at two different
    consolidations" — the case #850 is about.
    """

    async def get(self, url: str, *, params=None, headers=None):
        if "/filestore/" in url:
            return httpx.Response(
                200,
                text=(
                    "<html><body><h1>Bundesverfassung der Schweizerischen Eidgenossenschaft</h1>"
                    "<article><h2>Art. 1</h2><p>Das Schweizervolk und die Kantone ...</p></article>"
                    "<article><h2>Art. 2 Abs. 1</h2><p>Die Schweizerische Eidgenossenschaft "
                    "schützt die Freiheit ...</p></article>"
                    "<article><h2>Art. 3</h2><p>Die Kantone sind souverän ...</p></article>"
                    "</body></html>"
                ),
                headers={"content-type": "text/html; charset=utf-8"},
                request=httpx.Request("GET", url, params=params),
            )
        return await super().get(url, params=params, headers=headers)


async def _capture_at(monkeypatch: pytest.MonkeyPatch, as_of: str):
    monkeypatch.setattr(httpx, "AsyncClient", AnyConsolidationAsyncClient)
    provider = FedlexSparqlProvider()
    result = await provider.start_run(
        SimpleNamespace(),
        SimpleNamespace(
            acquisition_spec={
                "seed_url": "https://fedlex.data.admin.ch/eli/cc/1999/404",
                "sparql_endpoint": "https://fedlex.data.admin.ch/sparqlendpoint",
                "preferred_languages": ["de"],
                "max_expressions": 1,
                "as_of_date": as_of,
            }
        ),
        SimpleNamespace(run_id=f"run_{as_of}"),
    )
    return result.inline_resources[0]


@pytest.mark.asyncio
async def test_two_consolidations_of_one_act_acquire_to_one_document_identity(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    """Fedlex's counterpart to the LexFind case, and the reason #850 is per-provider.

    Here the *stable* URI is `source_url` (the act-level ELI) and the moving one is
    `final_url` (the filestore manifestation, whose path embeds the consolidation date).
    That is the exact opposite of `lexfind_api`, which is why no single global URL
    preference can serve both — the identity has to be stated by the provider.
    """
    earlier = await _capture_at(monkeypatch, "2023-01-01")
    later = await _capture_at(monkeypatch, "2025-01-01")

    # Non-vacuity: the two runs really did select different consolidations, so the URL
    # a `final_url`-first rule would key on genuinely moved.
    assert earlier.metadata["concrete_work_uri"].endswith("20220213")
    assert later.metadata["concrete_work_uri"].endswith("20240303")
    assert earlier.final_url != later.final_url
    assert "20220213" in earlier.final_url
    assert "20240303" in later.final_url

    assert (
        earlier.identity_locator
        == later.identity_locator
        == "https://fedlex.data.admin.ch/eli/cc/1999/404"
    )

    ((raw_earlier, _),) = ArtifactPipeline().normalize(run_id="run_a", resources=[earlier])
    ((raw_later, _),) = ArtifactPipeline().normalize(run_id="run_b", resources=[later])
    assert upstream_locator(raw_earlier.metadata) == upstream_locator(raw_later.metadata)
    assert "20220213" not in upstream_locator(raw_earlier.metadata)
    assert "20240303" not in upstream_locator(raw_later.metadata)


# ── SR collection enumeration ─────────────────────────────────────────────────
#
# Before this existed the provider could only acquire works pasted into
# `seed_urls`: the five enabled federal templates named 16 URIs between them and
# the deployed corpus held ONE federal document.


class _EnumerationClient(FakeAsyncClient):
    """Serves paged SR enumeration results, and records the offsets requested."""

    def __init__(self, pages: list[list[str]]) -> None:
        super().__init__()
        self._pages = pages
        self.offsets: list[int] = []

    async def get(self, url: str, *, params=None, headers=None):
        del headers
        query = (params or {}).get("query", "")
        request = httpx.Request("GET", url, params=params)
        offset = int(query.rsplit("OFFSET", 1)[1].strip())
        self.offsets.append(offset)
        index = offset // FedlexSparqlProvider._SR_ENUMERATION_PAGE_SIZE
        rows = self._pages[index] if index < len(self._pages) else []
        return httpx.Response(
            200,
            json={"results": {"bindings": [{"work": {"value": uri}} for uri in rows]}},
            request=request,
        )


def _cc(n: int) -> str:
    return f"https://fedlex.data.admin.ch/eli/cc/{n}/1"


@pytest.mark.asyncio
async def test_enumeration_walks_pages_and_dedupes() -> None:
    provider = FedlexSparqlProvider()
    page = FedlexSparqlProvider._SR_ENUMERATION_PAGE_SIZE
    # A full page forces a second request; the duplicate across pages must collapse.
    first = [_cc(i) for i in range(page)]
    second = [first[0], _cc(page + 1)]
    client = _EnumerationClient([first, second])

    uris, exhausted = await provider._enumerate_sr_work_uris(
        client=client, sparql_endpoint="https://fedlex.data.admin.ch/sparqlendpoint", limit=None
    )

    assert len(uris) == page + 1
    assert len(set(uris)) == len(uris), "duplicate work URIs across pages were not collapsed"
    assert exhausted is True
    assert client.offsets == [0, page], "paging did not advance by page size"


@pytest.mark.asyncio
async def test_enumeration_reports_truncation_rather_than_implying_a_whole_corpus() -> None:
    """`exhausted=False` is what stops a capped walk being read as the full SR."""
    provider = FedlexSparqlProvider()
    client = _EnumerationClient([[_cc(1), _cc(2), _cc(3)]])

    uris, exhausted = await provider._enumerate_sr_work_uris(
        client=client, sparql_endpoint="https://fedlex.data.admin.ch/sparqlendpoint", limit=2
    )

    assert uris == [_cc(1), _cc(2)]
    assert exhausted is False


@pytest.mark.asyncio
async def test_enumeration_ignores_uris_outside_the_sr_collection() -> None:
    """An AS/BBl URI is federal but is not the Systematic Collection."""
    provider = FedlexSparqlProvider()
    client = _EnumerationClient(
        [[_cc(1), "https://fedlex.data.admin.ch/eli/oc/2020/5", "https://example.com/eli/cc/9/9"]]
    )

    uris, _ = await provider._enumerate_sr_work_uris(
        client=client, sparql_endpoint="https://fedlex.data.admin.ch/sparqlendpoint", limit=None
    )

    assert uris == [_cc(1)]


def test_unknown_enumeration_strategy_is_refused_not_ignored() -> None:
    provider = FedlexSparqlProvider()
    with pytest.raises(ProviderConfigurationError, match="does not support enumeration"):
        provider._enumeration_strategy({"enumeration": "systematic_digit_union"})


def test_absent_enumeration_is_none_so_seeded_templates_are_unaffected() -> None:
    provider = FedlexSparqlProvider()
    assert provider._enumeration_strategy({}) is None
    assert provider._enumeration_strategy({"enumeration": ""}) is None


def test_plan_with_enumeration_needs_no_seed_urls() -> None:
    """A seeded plan raises without seeds; an enumerating one must not."""
    provider = FedlexSparqlProvider()
    version = SimpleNamespace(
        acquisition_spec={"enumeration": "sr_collection", "max_works": 50},
    )

    plan = provider.plan(SimpleNamespace(), version)

    assert plan.seed_urls == []
    assert plan.estimated_request_count == 50
    assert any("enumeration=sr_collection" in note for note in plan.notes)


def test_plan_without_enumeration_still_requires_seeds() -> None:
    provider = FedlexSparqlProvider()
    with pytest.raises(ProviderConfigurationError, match="requires acquisition_spec"):
        provider.plan(SimpleNamespace(), SimpleNamespace(acquisition_spec={}))
