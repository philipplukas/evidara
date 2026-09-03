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

import copy
import hashlib
import json
import logging
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
    verify_mirror_fidelity,
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
    # The mirror spot-check reaches the CANTON's host, not LexFind. Tests that
    # are not about it switch it off explicitly, so no test can accidentally
    # depend on a stub answering a request it never meant to make — and no test
    # can ever reach `notes.zh.ch` for real.
    spec.setdefault("mirror_spot_check_sample", 0)
    return SimpleNamespace(acquisition_spec=spec)


def _run(run_id="run_test"):
    return SimpleNamespace(run_id=run_id, scope={})


class _ScriptedClient:
    """httpx.AsyncClient stand-in replaying the captured search response."""

    def __init__(self, *args, pdf=_PDF, page=None, canton=None, **kwargs):
        del args, kwargs
        self._pdf = pdf
        self._page = page if page is not None else _FIXTURE
        # Absolute URL -> (content, content_type). Absent means the canton's host
        # does not answer, which is the #716 outage and NOT a divergence.
        self._canton = canton or {}
        self.pdf_requests: list[str] = []
        self.canton_requests: list[str] = []

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
        if url.startswith("http"):
            self.canton_requests.append(url)
            if url not in self._canton:
                raise httpx.ConnectError(f"no route to {url}")
            content, content_type = self._canton[url]
            return httpx.Response(
                200,
                content=content,
                headers={"content-type": content_type},
                request=httpx.Request("GET", url),
            )
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


def test_repealed_law_with_an_end_date_is_not_in_force_after_it():
    """The dated half of the trap: `version_inactive_since` must close the window.

    Deliberately leaves `is_active` at the fixture's `True`, so the
    `is_active is False` short-circuit cannot answer and the *date* branch is
    the only thing under test. Without this the branch had no coverage at all
    and a law repealed after capture read as in force forever.
    """
    version = dict(_current_version(_tol("554.5")))
    version.update(version_inactive_since="30.06.2026")
    assert version["is_active"] is True
    assert is_in_force(version, as_of="2026-07-01") is False


def test_the_inactive_since_date_is_the_first_day_out_of_force():
    """The boundary, asserted deliberately: `version_inactive_since` is EXCLUSIVE.

    LexFind's field says the version has been *out of force since* that date —
    the day its successor took over, mirroring `version_active_since`, which is
    the inclusive first day in force. So the last day in force is the day
    before. Guessing the other way would report a repealed norm as good law for
    one more day, which is the #661 failure at one-day resolution.

    **This is inference, not measurement**, and it is asserted here so that it
    is at least stated rather than assumed: the reading rests on the field name
    and on symmetry with `version_active_since`, and every
    `version_inactive_since` in the captured fixture is `null`, so nothing in
    this repo has yet observed a real one. A live probe against a superseded
    version would settle it.

    **#843** tracks the contradiction this sits next to: `temporal_metadata`
    (three tests up) ships that same date onward as `in_force_until`, which
    `legal-search/api/src/core/norm-hierarchy/in-force.ts:24-27,60` defines as
    INCLUSIVE — so the exclusive reading asserted here is silently widened by one
    day downstream. LexFind is the outlier; `ris_ogd` already emits inclusive.
    Do not "fix" one end of that without reading #843.
    """
    version = dict(_current_version(_tol("554.5")))
    version.update(version_inactive_since="30.06.2026")
    assert is_in_force(version, as_of="2026-06-29") is True
    assert is_in_force(version, as_of="2026-06-30") is False


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
    assert hundegesetz.metadata["in_force_at_capture"] is True


@pytest.mark.asyncio
async def test_capture_publishes_no_timeless_in_force_boolean(provider, monkeypatch):
    """A bare `in_force` becomes a lie the day the captured law is repealed.

    The window (`in_force_from` / `in_force_until`) is what travels; force on a
    given date is derived from it downstream, per document and per question.
    Acquisition may record only what it *observed* on the day it fetched, under
    a name that says so.
    """
    monkeypatch.setattr(
        "platform_control.services.lexfind_api_provider.httpx.AsyncClient", _client_factory()
    )
    result = await provider.start_run(
        SimpleNamespace(),
        _source_version(search_text="554", entity_ids=[26], max_documents=4),
        _run(),
    )
    for resource in result.inline_resources:
        assert "in_force" not in resource.metadata


@pytest.mark.asyncio
async def test_a_law_already_repealed_at_capture_is_observed_as_not_in_force(provider, monkeypatch):
    """Proves the observation is evaluated against a date, not assumed True.

    Feeds the real fixture back with one edit — the Hundegesetz version closed
    in 2020 — so the capture-time window is already shut. The interval still
    ships in full; only the observation flips.
    """
    page = copy.deepcopy(_FIXTURE)
    for tol in page["texts_of_law_with_matches"]:
        if tol["systematic_number"] == "554.5":
            for match in tol["matches"]:
                match["version_inactive_since"] = "30.06.2020"

    monkeypatch.setattr(
        "platform_control.services.lexfind_api_provider.httpx.AsyncClient",
        _client_factory(page=page),
    )
    result = await provider.start_run(
        SimpleNamespace(),
        _source_version(search_text="554", entity_ids=[26], max_documents=4),
        _run(),
    )
    hundegesetz = next(r for r in result.inline_resources if r.title == "Hundegesetz")
    assert hundegesetz.metadata["in_force_until"] == "2020-06-30"
    assert hundegesetz.metadata["in_force_at_capture"] is False


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


# --------------------------------------------------------------------------
# Enumeration and coverage reconciliation (#816)
# --------------------------------------------------------------------------


class _EnumerationClient:
    """Serves a distinct slice per digit, plus the published entity totals.

    Digits deliberately OVERLAP, because that is the real API's behaviour:
    matching is `contains`, so on ZH the ten queries report 2613 hits over 1377
    records. A union that failed to deduplicate would pass a test built on
    disjoint slices and capture the same law many times against production.
    """

    def __init__(self, *args, slices=None, totals=None, **kwargs):
        del args, kwargs
        # ids 1..5, each reachable from more than one digit.
        self._slices = (
            slices
            if slices is not None
            else {
                "0": [1],
                "1": [1, 2],
                "2": [2, 3],
                "3": [3, 4],
                "4": [4, 5],
                "5": [5, 1],
                "6": [],
                "7": [],
                "8": [],
                "9": [2],
            }
        )
        self._totals = totals
        self.payloads: list[dict] = []
        self._by_search: dict[int, str] = {}
        self._next_id = 0

    async def __aenter__(self):
        return self

    async def __aexit__(self, exc_type, exc, tb):
        del exc_type, exc, tb

    async def post(self, url, *, json=None):
        self.payloads.append(json)
        self._next_id += 1
        self._by_search[self._next_id] = json["search_text"]
        return httpx.Response(
            200,
            json={"id": self._next_id, "session_id": "s"},
            request=httpx.Request("POST", f"https://www.lexfind.ch{url}"),
        )

    async def get(self, url, *, params=None):
        request = httpx.Request("GET", f"https://www.lexfind.ch{url}")
        if url.startswith("/tol/"):
            return httpx.Response(
                200, content=_PDF, headers={"content-type": "application/pdf"}, request=request
            )
        if url.endswith("entities/extended"):
            body = (
                self._totals
                if self._totals is not None
                else [
                    {
                        "id": 26,
                        "status": {
                            "total_texts_of_law": 5,
                            "active_texts_of_law": 3,
                            "changes_in_last_n_days": 2,
                        },
                    }
                ]
            )
            return httpx.Response(200, json=body, request=request)
        search_id = int(url.rsplit("/", 1)[-1])
        digit = self._by_search[search_id]
        rows = [
            {
                "id": i,
                "systematic_number": f"55{i}",
                "entity": {"id": 26},
                "dta_urls": [
                    {"language": "de", "url": f"/tol/{i}/de", "original_url": f"https://zh/{i}"}
                ],
                "matches": [],
            }
            for i in self._slices.get(digit, [])
        ]
        return httpx.Response(
            200, json={"texts_of_law_with_matches": rows, "number_of_pages": 1}, request=request
        )


def _enum_factory(**kw):
    return lambda *a, **k: _EnumerationClient(*a, **kw, **k)


async def _enumerate(provider, monkeypatch, client, **spec):
    monkeypatch.setattr(
        "platform_control.services.lexfind_api_provider.httpx.AsyncClient",
        lambda *a, **k: client,
    )
    return await provider.start_run(
        SimpleNamespace(),
        _source_version(enumeration="systematic_digit_union", entity_ids=[26], **spec),
        _run(),
    )


@pytest.mark.asyncio
async def test_digit_union_queries_every_digit_and_deduplicates(provider, monkeypatch):
    """Ten queries, overlapping slices, five distinct laws — captured once each."""
    client = _EnumerationClient()
    result = await _enumerate(provider, monkeypatch, client)

    assert [p["search_text"] for p in client.payloads] == list("0123456789")
    assert len(result.inline_resources) == 5
    assert result.response_payload["captured"] == 5


@pytest.mark.asyncio
async def test_enumeration_includes_repealed_law(provider, monkeypatch):
    """`active_only` must be False, or a third of ZH's corpus goes missing while
    the run reconciles against 944 and looks correct."""
    client = _EnumerationClient()
    await _enumerate(provider, monkeypatch, client)

    assert all(p["active_only"] is False for p in client.payloads)
    assert all(p["search_in_systematic_number"] is True for p in client.payloads)


@pytest.mark.asyncio
async def test_coverage_is_complete_when_observed_matches_published(provider, monkeypatch):
    client = _EnumerationClient()
    result = await _enumerate(provider, monkeypatch, client)

    coverage = result.response_payload["coverage"]
    assert coverage["complete"] is True
    assert coverage["denominator_tier"] == "published"
    assert coverage["entities"] == [
        {"entity_id": 26, "expected": 5, "observed": 5, "gap": 0, "changed_last_30d": 2}
    ]


@pytest.mark.asyncio
async def test_coverage_reports_the_gap_rather_than_a_pass(provider, monkeypatch):
    """Published 9, found 5 — the run must say 4 short, not report success."""
    client = _EnumerationClient(
        totals=[{"id": 26, "status": {"total_texts_of_law": 9, "active_texts_of_law": 9}}]
    )
    result = await _enumerate(provider, monkeypatch, client)

    coverage = result.response_payload["coverage"]
    assert coverage["complete"] is False
    assert coverage["entities"][0]["gap"] == 4


@pytest.mark.asyncio
async def test_unknown_denominator_never_rounds_up_to_complete(provider, monkeypatch):
    """An entity LexFind does not report has no denominator, so completeness is
    unstatable — never True. This is the failure the ledger exists to prevent."""
    client = _EnumerationClient(totals=[])
    result = await _enumerate(provider, monkeypatch, client)

    coverage = result.response_payload["coverage"]
    assert coverage["complete"] is False
    assert coverage["entities"][0]["expected"] is None
    assert coverage["entities"][0]["gap"] is None


@pytest.mark.asyncio
async def test_max_documents_downgrades_the_completeness_claim(provider, monkeypatch):
    """A capped run is a sample. `complete: true` beside 2 of 5 documents would be
    the exact overstatement this reconciliation exists to stop."""
    client = _EnumerationClient()
    result = await _enumerate(provider, monkeypatch, client, max_documents=2)

    coverage = result.response_payload["coverage"]
    assert coverage["complete"] is False
    assert coverage["truncated_by_max_documents"] is True
    assert len(result.inline_resources) == 2


@pytest.mark.asyncio
async def test_enumeration_without_entity_ids_is_refused(provider, monkeypatch):
    """Unscoped, this would sweep all 28 entities from a config that looks
    unremarkable."""
    monkeypatch.setattr(
        "platform_control.services.lexfind_api_provider.httpx.AsyncClient",
        lambda *a, **k: _EnumerationClient(),
    )
    result = await provider.start_run(
        SimpleNamespace(),
        _source_version(enumeration="systematic_digit_union"),
        _run(),
    )
    assert result.inline_resources == []
    assert "entity_ids is required" in result.inline_failure_reason


@pytest.mark.asyncio
async def test_unsupported_enumeration_strategy_is_named(provider, monkeypatch):
    monkeypatch.setattr(
        "platform_control.services.lexfind_api_provider.httpx.AsyncClient",
        lambda *a, **k: _EnumerationClient(),
    )
    result = await provider.start_run(
        SimpleNamespace(),
        _source_version(enumeration="id_sweep", entity_ids=[26]),
        _run(),
    )
    assert result.inline_resources == []
    assert "is not supported" in result.inline_failure_reason


def test_search_templates_still_report_the_coverage_limit(provider):
    """A search-scoped template must keep saying it holds a branch, not a corpus."""
    plan = provider.plan(SimpleNamespace(), _source_version(search_text="554", entity_ids=[26]))
    assert any("COVERAGE LIMIT" in note for note in plan.notes)


def test_enumerating_plan_reports_the_verified_measurement(provider):
    plan = provider.plan(
        SimpleNamespace(),
        _source_version(enumeration="systematic_digit_union", entity_ids=[26]),
    )
    assert any("ENUMERATION" in note for note in plan.notes)
    assert not any("COVERAGE LIMIT" in note for note in plan.notes)
    assert not any("search_text is missing" in note for note in plan.notes)


@pytest.mark.asyncio
async def test_zero_published_total_is_unstatable_not_complete(provider, monkeypatch):
    """A reported entity with a zero/missing count must not read as fully covered.

    `int(... or 0)` used to turn a missing `total_texts_of_law` into `expected: 0`, and
    `observed == 0` against `expected == 0` left `complete: True` — "this canton
    publishes zero laws and we hold all zero of them". The existing
    `test_unknown_denominator_never_rounds_up_to_complete` misses it: that covers the
    ABSENT entity, this covers the empty count.
    """
    client = _EnumerationClient(
        slices=dict.fromkeys("0123456789", []),
        totals=[{"id": 26, "status": {"total_texts_of_law": 0, "active_texts_of_law": 0}}],
    )
    result = await _enumerate(provider, monkeypatch, client)

    coverage = result.response_payload["coverage"]
    assert coverage["entities"][0]["expected"] is None
    assert coverage["entities"][0]["gap"] is None
    assert coverage["complete"] is False


@pytest.mark.asyncio
async def test_missing_total_key_is_unstatable(provider, monkeypatch):
    client = _EnumerationClient(totals=[{"id": 26, "status": {"active_texts_of_law": 3}}])
    result = await _enumerate(provider, monkeypatch, client)

    coverage = result.response_payload["coverage"]
    assert coverage["entities"][0]["expected"] is None
    assert coverage["complete"] is False


# --------------------------------------------------------------------------
# Provenance may not degrade to the mirror (#731)
# --------------------------------------------------------------------------

_ZH_ERLASS_URL = (
    "https://www.zh.ch/de/politik-staat/gesetze-beschluesse/gesetzessammlung/"
    "zhlex-ls/erlass-554_5-2008_04_14-2010_01_01-129.html"
)
_ZH_FILE_URL = "https://www.notes.zh.ch/appl/zhlex_r.nsf/WebView/$File/554.5.pdf"

# The JavaScript stub #716 found and 2026-09-03 re-measured: the reason the
# erlass page looks empty to a deterministic fetch.
_ZH_STUB = (
    b"<html><head><script>window.location.href='"
    + _ZH_FILE_URL.encode()
    + b"';</script></head><body>Redirecting...</body></html>"
)


def _page_without_original_url(systematic_number: str) -> dict:
    page = copy.deepcopy(_FIXTURE)
    for tol in page["texts_of_law_with_matches"]:
        if tol["systematic_number"] == systematic_number:
            for entry in tol["dta_urls"]:
                entry.pop("original_url", None)
    return page


@pytest.mark.asyncio
async def test_a_record_without_original_url_is_refused_not_mirrored(provider, monkeypatch):
    """The canton's page is what makes a mirrored capture admissible.

    This used to be `if original_url:`, with `source_url=original_url or <the
    LexFind URL>`: when LexFind omitted the field, the capture silently recorded
    the MIRROR as the document's source. Refuse instead, and name the reason.
    """
    monkeypatch.setattr(
        "platform_control.services.lexfind_api_provider.httpx.AsyncClient",
        _client_factory(page=_page_without_original_url("554.5")),
    )
    result = await provider.start_run(
        SimpleNamespace(), _source_version(search_text="554", entity_ids=[26]), _run()
    )

    assert "Hundegesetz" not in [r.title for r in result.inline_resources]
    assert [s["reason"] for s in result.response_payload["skipped"]] == ["original_url_missing"]


@pytest.mark.asyncio
async def test_no_captured_resource_ever_cites_the_mirror_as_its_source(provider, monkeypatch):
    monkeypatch.setattr(
        "platform_control.services.lexfind_api_provider.httpx.AsyncClient", _client_factory()
    )
    result = await provider.start_run(
        SimpleNamespace(), _source_version(search_text="554", entity_ids=[26]), _run()
    )

    assert result.inline_resources
    for resource in result.inline_resources:
        assert not resource.source_url.startswith("https://www.lexfind.ch")
        assert resource.metadata["original_url"] == resource.source_url


# --------------------------------------------------------------------------
# Byte-identity is re-checked, not remembered (#731)
# --------------------------------------------------------------------------


@pytest.mark.asyncio
async def test_identity_holds_when_the_canton_serves_the_same_bytes():
    client = _ScriptedClient(canton={_ZH_ERLASS_URL: (_PDF, "application/pdf")})
    result = await verify_mirror_fidelity(
        client, original_url=_ZH_ERLASS_URL, mirrored_body=_PDF, tol_id=22871
    )

    assert result.status == "identical"
    assert result.diverged is False
    # Both hashes recorded even on agreement: "we checked and they matched" is
    # the evidence; "nothing was reported" is not.
    assert result.mirror_md5 == result.source_md5 == hashlib.md5(_PDF).hexdigest()


@pytest.mark.asyncio
async def test_the_resolver_follows_the_js_stub_to_the_canton_file():
    """The measured ZH chain: erlass page -> a JS stub -> `WebView/$File/` -> PDF.

    The middle hop is #716 exactly — a URL that looks like a download and answers
    `200` with a few hundred bytes of JavaScript. Two hops is the ceiling.
    """
    attachment_url = "https://www.notes.zh.ch/appl/zhlex_r.nsf/OpenAttachment/$File/554.5.pdf"
    client = _ScriptedClient(
        canton={
            _ZH_ERLASS_URL: (
                b'<html><a href="' + attachment_url.encode() + b'">Erlasstext</a></html>',
                "text/html",
            ),
            attachment_url: (_ZH_STUB, "text/html"),
            _ZH_FILE_URL: (_PDF, "application/pdf"),
        }
    )
    result = await verify_mirror_fidelity(client, original_url=_ZH_ERLASS_URL, mirrored_body=_PDF)

    assert result.status == "identical"
    assert result.source_document_url == _ZH_FILE_URL


@pytest.mark.asyncio
async def test_a_divergence_is_reported_with_both_hashes_not_swallowed():
    client = _ScriptedClient(canton={_ZH_ERLASS_URL: (_PDF + b"amended\n", "application/pdf")})
    result = await verify_mirror_fidelity(
        client, original_url=_ZH_ERLASS_URL, mirrored_body=_PDF, tol_id=22871
    )

    assert result.status == "diverged"
    assert result.diverged is True
    assert result.mirror_md5 != result.source_md5
    assert result.mirror_md5 in result.detail
    assert result.source_md5 in result.detail


@pytest.mark.asyncio
async def test_an_unreachable_canton_is_not_a_divergence():
    """#716 was seven weeks long. The mirror exists to survive exactly this.

    Reporting an outage as a divergence would fail every run for as long as the
    canton is down — handing the outage the power the mirror was chosen to deny
    it.
    """
    client = _ScriptedClient(canton={})
    result = await verify_mirror_fidelity(client, original_url=_ZH_ERLASS_URL, mirrored_body=_PDF)

    assert result.status == "source_unreachable"
    assert result.diverged is False


@pytest.mark.asyncio
async def test_a_page_leading_nowhere_is_unverified_not_verified():
    client = _ScriptedClient(canton={_ZH_ERLASS_URL: (b"<html>no link here</html>", "text/html")})
    result = await verify_mirror_fidelity(client, original_url=_ZH_ERLASS_URL, mirrored_body=_PDF)

    assert result.status == "source_document_not_found"
    assert result.source_md5 is None


@pytest.mark.asyncio
async def test_the_run_fails_loudly_when_the_mirror_has_diverged(provider, monkeypatch, caplog):
    monkeypatch.setattr(
        "platform_control.services.lexfind_api_provider.httpx.AsyncClient",
        _client_factory(canton={_ZH_ERLASS_URL: (_PDF + b"amended\n", "application/pdf")}),
    )
    with caplog.at_level(logging.ERROR):
        result = await provider.start_run(
            SimpleNamespace(),
            _source_version(
                search_text="554",
                entity_ids=[26],
                mirror_spot_check_sample=4,
                mirror_spot_check_delay_seconds=0,
            ),
            _run(),
        )

    fidelity = result.response_payload["mirror_fidelity"]
    assert fidelity["diverged"] >= 1
    assert result.inline_failure_reason is not None
    assert "mirror fidelity check FAILED" in result.inline_failure_reason
    assert any("mirror diverged" in record.message for record in caplog.records)


@pytest.mark.asyncio
async def test_an_unreachable_canton_does_not_fail_the_run(provider, monkeypatch):
    monkeypatch.setattr(
        "platform_control.services.lexfind_api_provider.httpx.AsyncClient",
        _client_factory(canton={}),
    )
    result = await provider.start_run(
        SimpleNamespace(),
        _source_version(
            search_text="554",
            entity_ids=[26],
            mirror_spot_check_sample=2,
            mirror_spot_check_delay_seconds=0,
        ),
        _run(),
    )

    fidelity = result.response_payload["mirror_fidelity"]
    assert fidelity["diverged"] == 0
    assert fidelity["unverified"] == 2
    assert result.inline_failure_reason is None
    assert len(result.inline_resources) == 4


@pytest.mark.asyncio
async def test_the_spot_check_is_a_sample_not_a_second_fetch_per_capture(provider, monkeypatch):
    """Doubling every acquisition's request count is not an acceptable price."""
    clients: list[_ScriptedClient] = []

    def factory(*a, **k):
        client = _ScriptedClient(*a, canton={_ZH_ERLASS_URL: (_PDF, "application/pdf")}, **k)
        clients.append(client)
        return client

    monkeypatch.setattr("platform_control.services.lexfind_api_provider.httpx.AsyncClient", factory)
    # Deliberately NOT `_source_version`: that helper switches the check off, and
    # this test is about the shipped default sample of one.
    result = await provider.start_run(
        SimpleNamespace(),
        SimpleNamespace(
            acquisition_spec={
                "search_text": "554",
                "entity_ids": [26],
                "mirror_spot_check_delay_seconds": 0,
            }
        ),
        _run(),
    )

    canton_requests = [url for client in clients for url in client.canton_requests]
    assert len(result.inline_resources) == 4
    assert result.response_payload["mirror_fidelity"]["sampled"] == 1  # the default
    assert len(canton_requests) == 1


@pytest.mark.asyncio
async def test_the_spot_check_can_be_switched_off_entirely(provider, monkeypatch):
    monkeypatch.setattr(
        "platform_control.services.lexfind_api_provider.httpx.AsyncClient", _client_factory()
    )
    result = await provider.start_run(
        SimpleNamespace(),
        _source_version(search_text="554", entity_ids=[26], mirror_spot_check_sample=0),
        _run(),
    )

    # Absent, not `verified: false`: a key that appears only when a check ran
    # cannot be misread as a check that passed.
    assert "mirror_fidelity" not in result.response_payload
