"""Tests for the LexFind provider (#731), driven by a REAL captured response.

`tests/fixtures/lexfind/search-zh-554.json` is an unedited capture of

    POST /api/frontend/v1/de/fulltext-search
      {"search_text": "554", "search_in_systematic_number": true,
       "entity_filter": [26], ...}
    GET  /api/frontend/v1/de/fulltext-search/{id}?...

taken 2026-07-22. It returns the whole ZH animal-protection branch -- 554.1,
554.11, 554.5, 554.51 -- which is exactly ADR-0033's cantonal rung.

Using the real payload is the point. The first version of these tests used
fixtures I invented from the issue description, and they passed against a
provider that read the wrong response key and would have emitted `01.06.2025`
into an ISO date field. Invented fixtures test the author's belief, not the
service.
"""

from __future__ import annotations

import json
from pathlib import Path
from types import SimpleNamespace

import httpx
import pytest

from platform_control.services.lexfind_api_provider import (
    LexFindApiProvider,
    _current_version,
    _iso_date_or_none,
    is_in_force,
    temporal_metadata,
)

_FIXTURE = json.loads(
    (Path(__file__).parent.parent / "fixtures" / "lexfind" / "search-zh-554.json").read_text()
)
_SESSION = {"id": _FIXTURE["id"], "session_id": _FIXTURE["session_id"]}

# Structurally honest PDF, over the default floor.
_PDF = b"%PDF-1.7\n" + b"1 0 obj\n<< /Type /Catalog >>\nendobj\n" * 120 + b"%%EOF\n"

# #716, reproduced: 200 OK carrying a redirect stub where a PDF was expected.
_STUB = (
    b"<html><head><script>window.location.href='/OpenAttachment?id=1';"
    b"</script></head><body>Redirecting...</body></html>"
)


def _tol(systematic_number: str) -> dict:
    return next(
        t
        for t in _FIXTURE["texts_of_law_with_matches"]
        if t["systematic_number"] == systematic_number
    )


def _source_version(**spec):
    return SimpleNamespace(acquisition_spec=spec)


def _run(run_id="run_test"):
    return SimpleNamespace(run_id=run_id, scope={})


class _ScriptedClient:
    """httpx.AsyncClient stand-in replaying the captured search response."""

    def __init__(self, *args, pdf=_PDF, page=None, **kwargs):
        del args, kwargs
        self._pdf = pdf
        self._page = page if page is not None else _FIXTURE
        self.pdf_requests: list[str] = []

    async def __aenter__(self):
        return self

    async def __aexit__(self, exc_type, exc, tb):
        del exc_type, exc, tb

    async def post(self, url, *, json=None):
        del json
        return httpx.Response(
            200, json=_SESSION, request=httpx.Request("POST", f"https://www.lexfind.ch{url}")
        )

    async def get(self, url, *, params=None):
        del params
        request = httpx.Request("GET", f"https://www.lexfind.ch{url}")
        if url.startswith("/tol/") or url.startswith("/tolv/"):
            self.pdf_requests.append(url)
            return httpx.Response(
                200,
                content=self._pdf,
                headers={"content-type": "application/pdf"},
                request=request,
            )
        return httpx.Response(200, json=self._page, request=request)


def _client_factory(**kw):
    return lambda *a, **k: _ScriptedClient(*a, **kw, **k)


@pytest.fixture
def provider():
    return LexFindApiProvider()


# --------------------------------------------------------------------------
# Date format — LexFind publishes DD.MM.YYYY, not ISO
# --------------------------------------------------------------------------


def test_swiss_date_is_converted_to_iso():
    """The live format. Passing it through unconverted is a wrong in-force date."""
    assert _iso_date_or_none("01.06.2025") == "2025-06-01"
    assert _iso_date_or_none("14.04.2008") == "2008-04-14"


def test_iso_input_is_accepted_unchanged():
    """So a format change on their side does not silently drop every date."""
    assert _iso_date_or_none("2025-06-01") == "2025-06-01"


def test_unrecognised_date_shape_is_dropped_not_guessed():
    """A mangled date is worse than an absent one -- absence can say 'unknown'."""
    assert _iso_date_or_none("June 2025") is None
    assert _iso_date_or_none("") is None
    assert _iso_date_or_none(None) is None


def test_real_fixture_dates_round_trip_to_iso():
    version = _current_version(_tol("554.5"))
    assert version["version_active_since"] == "01.06.2025"  # as published
    assert temporal_metadata(version)["in_force_from"] == "2025-06-01"  # as emitted


# --------------------------------------------------------------------------
# Response shape — the keys that are easy to get wrong
# --------------------------------------------------------------------------


def test_temporal_fields_live_on_the_version_not_the_record():
    """Reading them from the record root yields nothing, silently."""
    record = _tol("554.5")
    assert "version_active_since" not in record
    assert _current_version(record)["version_active_since"] == "01.06.2025"


def test_current_version_is_preferred_over_the_first():
    record = _tol("554.5")
    assert _current_version(record)["info_badge"] == "current"


def test_results_key_is_not_the_hit_list():
    """`results` is a per-language COUNT array, not the documents."""
    assert all("number_of_results" in row for row in _FIXTURE["results"])
    assert len(_FIXTURE["texts_of_law_with_matches"]) == 4


# --------------------------------------------------------------------------
# Temporal validity — the #661 trap
# --------------------------------------------------------------------------


def test_active_law_maps_its_in_force_start():
    meta = temporal_metadata(_current_version(_tol("554.51")))
    assert meta["in_force_from"] == "2025-06-01"
    assert "in_force_until" not in meta


def test_repealed_law_carries_its_end_date():
    version = dict(_current_version(_tol("554.5")))
    version.update(version_inactive_since="30.06.2020", is_active=False)
    meta = temporal_metadata(version)
    assert meta["in_force_until"] == "2020-06-30"
    assert meta["amendment_relation"] == "repealed_by"


def test_repeal_without_an_end_date_is_recorded_without_inventing_one():
    """We know it is repealed; we do not know when. Different facts."""
    version = dict(_current_version(_tol("554.5")))
    version.update(version_inactive_since=None, is_active=False)
    meta = temporal_metadata(version)
    assert meta["amendment_relation"] == "repealed_by"
    assert "in_force_until" not in meta


def test_repealed_law_is_not_reported_in_force_despite_an_open_window():
    """The #661 trap, asserted directly: `is_active: False` must win."""
    version = dict(_current_version(_tol("554.5")))
    version.update(version_inactive_since=None, is_active=False)
    assert is_in_force(version, as_of="2026-07-22") is False


def test_active_law_inside_its_window_is_in_force():
    assert is_in_force(_current_version(_tol("554.5")), as_of="2026-07-22") is True


def test_law_before_its_start_is_not_yet_in_force():
    assert is_in_force(_current_version(_tol("554.5")), as_of="2025-05-31") is False


def test_missing_start_date_is_unknown_not_false():
    assert is_in_force({"title": "x"}) is None


def test_unknown_dates_are_absent_not_defaulted():
    assert temporal_metadata({"title": "x"}) == {}


# --------------------------------------------------------------------------
# Discovery and capture
# --------------------------------------------------------------------------


@pytest.mark.asyncio
async def test_systematic_prefix_discovers_the_whole_branch(provider, monkeypatch):
    """554 -> the four ZH animal-protection acts, ADR-0033's cantonal rung."""
    monkeypatch.setattr(
        "platform_control.services.lexfind_api_provider.httpx.AsyncClient", _client_factory()
    )
    result = await provider.start_run(
        SimpleNamespace(),
        _source_version(search_text="554", entity_ids=[26]),
        _run(),
    )
    assert len(result.inline_resources) == 4
    titles = sorted(r.title for r in result.inline_resources)
    assert "Hundegesetz" in titles
    assert "Hundeverordnung" in titles


@pytest.mark.asyncio
async def test_capture_carries_canton_provenance_not_the_mirror(provider, monkeypatch):
    monkeypatch.setattr(
        "platform_control.services.lexfind_api_provider.httpx.AsyncClient", _client_factory()
    )
    result = await provider.start_run(
        SimpleNamespace(),
        _source_version(search_text="554", entity_ids=[26], max_documents=4),
        _run(),
    )
    hundegesetz = next(r for r in result.inline_resources if r.title == "Hundegesetz")
    assert hundegesetz.is_binary
    assert hundegesetz.source_url.startswith("https://www.zh.ch/")
    assert "erlass-554_5" in hundegesetz.metadata["original_url"]
    assert hundegesetz.metadata["systematic_number"] == "554.5"
    assert hundegesetz.metadata["lexfind_entity"] == "ZH"
    assert hundegesetz.metadata["in_force_from"] == "2025-06-01"
    assert hundegesetz.metadata["in_force"] is True


@pytest.mark.asyncio
async def test_download_url_comes_from_the_record_not_a_guess(provider, monkeypatch):
    factory_client = {}

    def factory(*a, **k):
        client = _ScriptedClient(*a, **k)
        factory_client["c"] = client
        return client

    monkeypatch.setattr("platform_control.services.lexfind_api_provider.httpx.AsyncClient", factory)
    await provider.start_run(
        SimpleNamespace(), _source_version(search_text="554", entity_ids=[26]), _run()
    )
    assert "/tol/22871/de" in factory_client["c"].pdf_requests


@pytest.mark.asyncio
async def test_716_stub_is_refused_and_recorded(provider, monkeypatch):
    monkeypatch.setattr(
        "platform_control.services.lexfind_api_provider.httpx.AsyncClient",
        _client_factory(pdf=_STUB),
    )
    result = await provider.start_run(
        SimpleNamespace(), _source_version(search_text="554", entity_ids=[26]), _run()
    )
    assert result.inline_resources == []
    assert {s["reason"] for s in result.response_payload["skipped"]} == {
        "html_where_binary_expected"
    }


@pytest.mark.asyncio
async def test_undersized_pdf_is_refused(provider, monkeypatch):
    monkeypatch.setattr(
        "platform_control.services.lexfind_api_provider.httpx.AsyncClient",
        _client_factory(pdf=b"%PDF-1.7\n%%EOF\n"),
    )
    result = await provider.start_run(
        SimpleNamespace(),
        _source_version(search_text="554", entity_ids=[26], min_pdf_bytes=5_000),
        _run(),
    )
    assert result.inline_resources == []
    assert result.response_payload["skipped"][0]["reason"] == "below_size_floor"


@pytest.mark.asyncio
async def test_binary_abstention_of_the_content_gate_is_recorded_not_implied(provider, monkeypatch):
    """Silence would read as 'assessed and passed'. ADR-0047 turns on this."""
    monkeypatch.setattr(
        "platform_control.services.lexfind_api_provider.httpx.AsyncClient", _client_factory()
    )
    result = await provider.start_run(
        SimpleNamespace(), _source_version(search_text="554", entity_ids=[26]), _run()
    )
    meta = result.inline_resources[0].metadata
    assert meta["legal_text_assessment"] == "abstained_binary_manifestation"


@pytest.mark.asyncio
async def test_max_documents_bounds_the_run(provider, monkeypatch):
    monkeypatch.setattr(
        "platform_control.services.lexfind_api_provider.httpx.AsyncClient", _client_factory()
    )
    result = await provider.start_run(
        SimpleNamespace(),
        _source_version(search_text="554", entity_ids=[26], max_documents=2),
        _run(),
    )
    assert len(result.inline_resources) == 2


@pytest.mark.asyncio
async def test_missing_search_text_fails_named_without_a_request(provider, monkeypatch):
    """LexFind has no list-everything call; an empty search_text is a 400.

    The operator must see the configuration error named, not a transport failure.
    """

    def explode(*a, **k):
        raise AssertionError("no request may be made without search_text")

    monkeypatch.setattr("platform_control.services.lexfind_api_provider.httpx.AsyncClient", explode)
    result = await provider.start_run(SimpleNamespace(), _source_version(entity_ids=[26]), _run())
    assert result.inline_resources == []
    assert "search_text is required" in result.inline_failure_reason


# --------------------------------------------------------------------------
# Readiness and plan honesty
# --------------------------------------------------------------------------


def test_readiness_is_live_on_three_cantons_of_acceptance_evidence(provider):
    """Promoted 2026-07-28 on ZH + BE + BS, all live, all `skipped_gates=[]`.

    Asserted as a distinct value rather than "not awaiting_evidence", because
    SCAFFOLD is the correct rollback target and AWAITING_EVIDENCE is not: only the
    latter waives the operator's config key for acceptance runs, so rolling back to
    it would re-open the route a rollback is closing.
    """
    assert provider.readiness.value == "live"


def test_plan_reports_the_search_contract_as_verified(provider):
    plan = provider.plan(SimpleNamespace(), _source_version(search_text="554", entity_ids=[26]))
    assert plan.raw["search_payload_verified"] is True
    assert plan.provider == "lexfind_api"
    assert plan.max_discovery_depth == 0


def test_plan_warns_when_no_entity_is_scoped(provider):
    plan = provider.plan(SimpleNamespace(), _source_version(search_text="554"))
    assert any("entity_ids" in note for note in plan.notes)
