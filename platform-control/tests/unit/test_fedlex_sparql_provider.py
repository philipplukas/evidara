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
