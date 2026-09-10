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

import asyncio
import copy
import hashlib
import json
import logging
from pathlib import Path
from types import SimpleNamespace

import httpx
import pytest

from acquisition_core.identity import upstream_locator
from acquisition_core.normalization import ArtifactPipeline
from platform_control.services.lexfind_api_provider import (
    LexFindApiProvider,
    _current_version,
    _iso_date_or_none,
    is_in_force,
    source_link_candidates,
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
    """The end date survives — converted, because the two sides differ (#843).

    `version_inactive_since` is EXCLUSIVE (the first day out of force) and
    `in_force_until` is INCLUSIVE (the last day in force), so 30 June in is 29
    June out. Before #843 this asserted `2020-06-30` and thereby pinned the
    off-by-one: the norm read as good law on the very day it stopped applying.
    """
    version = dict(_current_version(_tol("554.5")))
    version.update(version_inactive_since="30.06.2020", is_active=False)
    meta = temporal_metadata(version)
    assert meta["in_force_until"] == "2020-06-29"
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
    """The boundary: `version_inactive_since` is EXCLUSIVE. **Now measured (#843).**

    This docstring used to say the reading was inference from the field name plus
    symmetry with `version_active_since`, because every `version_inactive_since`
    in the captured fixture is `null`. It was measured live on 2026-09-03 and the
    inference held:

      * `GET /api/frontend/v1/de/texts-of-law/22871/with-version-groups` (the ZH
        Hundegesetz) returns 7 versions and `version_inactive_since` is `null` on
        ALL of them, six of which are `is_active: false`. So the field is not a
        version-window end; it is the **repeal date of the act**, mirrored by
        `info_badge: abrogated` + `info_badge_date`.
      * `GET /api/frontend/v1/de/entities/{26,1}/recent-changes` (ZH and BE, five
        pages each) returned 150 changes, 27 with a non-null
        `version_inactive_since`. **26 of the 27 fall on the 1st of a month** and
        not one is a month-end. Swiss repeals take effect at the start of a
        month, so a "last day in force" field would cluster on 30/31. This one
        holds the day the repeal took effect — the first day OUT of force.

    That prose also used to end "LexFind is the outlier; `ris_ogd` already emits
    inclusive". The conclusion survives measurement but the reasoning did not:
    `ris_ogd` did not *emit* inclusive, it passed its upstream value through
    untouched, and nothing had established what that value meant. RIS is now
    measured inclusive too (see `test_ris_ogd_provider.py`), so the passthrough is
    correct — but it was correct by luck, and this file was asserting it as
    though it were by design.
    """
    version = dict(_current_version(_tol("554.5")))
    version.update(version_inactive_since="30.06.2026")
    assert is_in_force(version, as_of="2026-06-29") is True
    assert is_in_force(version, as_of="2026-06-30") is False


def test_the_exclusive_upstream_end_date_is_converted_to_the_inclusive_boundary():
    """The producer half of a two-sided pin on ONE boundary date (#843).

    The consumer half is `legal-search/api/src/core/norm-hierarchy/in-force.spec.ts`
    "agrees with the producers on ONE boundary date, deliberately (#843)", which
    consumes exactly the `2026-06-30` this emits.

    The input is a real record, not an invented one: ZH 415.611, read from
    `/entities/26/recent-changes` on 2026-09-03 — `version_active_since:
    "01.02.2017"`, `version_inactive_since: "01.07.2026"`, `info_badge:
    "abrogated"`. The act was repealed with effect from 1 July 2026, so 30 June is
    the last day it applied.

    Before #843, `temporal_metadata` shipped `2026-07-01` into an `in_force_until`
    that `resolveInForceState` reads inclusively — so the repealed act read as
    `in_force` on its own repeal date. The two files agreed on `is_in_force`
    (exclusive) and disagreed on the metadata (inclusive) for the same record,
    which is the defect #843 was filed for.
    """
    version = dict(_current_version(_tol("554.5")))
    version.update(version_active_since="01.02.2017", version_inactive_since="01.07.2026")

    meta = temporal_metadata(version)
    assert meta["in_force_from"] == "2017-02-01"
    assert meta["in_force_until"] == "2026-06-30"

    # And the provider's own three-valued answer agrees with the metadata it
    # emits, on the boundary date and on the day after. It did not before.
    assert is_in_force(version, as_of="2026-06-30") is True
    assert is_in_force(version, as_of="2026-07-01") is False


def test_a_month_boundary_end_date_does_not_roll_back_into_the_wrong_month():
    """Crossing a month/year edge is where a naive `-1 day` would break.

    `01.01.2026` out is `2025-12-31` in — not `2026-01-00`, and not `2026-12-31`.
    Cheap to assert, and the arithmetic is the whole of the fix.
    """
    version = dict(_current_version(_tol("554.5")))
    version.update(version_inactive_since="01.01.2026")
    assert temporal_metadata(version)["in_force_until"] == "2025-12-31"

    version.update(version_inactive_since="01.03.2024")  # leap year
    assert temporal_metadata(version)["in_force_until"] == "2024-02-29"


def test_an_unparseable_end_date_is_dropped_rather_than_shifted():
    """A mangled boundary is worse than an absent one: absence resolves `unknown`."""
    version = dict(_current_version(_tol("554.5")))
    version.update(version_inactive_since="irgendwann")
    assert "in_force_until" not in temporal_metadata(version)


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
    # `30.06.2020` upstream is EXCLUSIVE, so the last day in force is 29 June
    # (#843). This is the end-to-end proof that the conversion in
    # `temporal_metadata` reaches `ProviderResource.metadata`, which is the path
    # the bundle hints and then the index read.
    assert hundegesetz.metadata["in_force_until"] == "2020-06-29"
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
    assert fidelity["proven"] is False
    assert result.inline_failure_reason is not None
    assert "mirror fidelity check FAILED" in result.inline_failure_reason
    assert any("mirror diverged" in record.message for record in caplog.records)


@pytest.mark.asyncio
async def test_a_divergence_discards_the_batch_instead_of_publishing_it(provider, monkeypatch):
    """Failing the run is NOT enough — `_dispatch_run` publishes first.

    `run_service._dispatch_run` persists `inline_resources` and builds the bundle
    events (`:1320-1345`) BEFORE it reads `inline_failure_reason` (`:1348-1353`),
    and `_publish_pending_dispatch_events` (`:1765-1787`) publishes every
    `raw_artifact.available` / `artifact_bundle.available` with no check on
    `run.status`. Handing resources down beside a failure reason would therefore
    put the divergent documents in the index — cited to the canton's own URL —
    and mark the run red afterwards, making the check worse than no check.

    The whole batch goes, not just the sampled document: a mirror that has
    stopped being faithful is not trustworthy for the records we did not draw.
    """
    monkeypatch.setattr(
        "platform_control.services.lexfind_api_provider.httpx.AsyncClient",
        _client_factory(canton={_ZH_ERLASS_URL: (_PDF + b"amended\n", "application/pdf")}),
    )
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

    assert result.inline_resources == []
    assert result.response_payload["captured"] == 4  # what was fetched
    assert result.response_payload["published"] == 0  # what was handed downstream
    assert "DISCARDED unpublished" in result.inline_failure_reason


@pytest.mark.asyncio
async def test_a_clean_run_still_publishes_everything_it_captured(provider, monkeypatch):
    """The negative control for the discard: it must not fire when nothing diverged."""
    monkeypatch.setattr(
        "platform_control.services.lexfind_api_provider.httpx.AsyncClient",
        _client_factory(canton={_ZH_ERLASS_URL: (_PDF, "application/pdf")}),
    )
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

    assert len(result.inline_resources) == 4
    assert result.response_payload["published"] == 4
    assert result.response_payload["mirror_fidelity"]["proven"] is True
    assert result.inline_failure_reason is None


# --------------------------------------------------------------------------
# An unverified check is not a passed check (#731)
# --------------------------------------------------------------------------


@pytest.mark.asyncio
async def test_an_unverified_check_says_so_in_the_log_not_only_in_a_count(
    provider, monkeypatch, caplog
):
    """A count buried in a job payload is the marker nothing reads."""
    monkeypatch.setattr(
        "platform_control.services.lexfind_api_provider.httpx.AsyncClient",
        _client_factory(canton={}),
    )
    with caplog.at_level(logging.WARNING):
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
    assert fidelity["unverified"] == 2
    assert fidelity["proven"] is False
    assert any("mirror NOT verified" in record.message for record in caplog.records)
    # And the stronger statement: this run proved nothing at all.
    assert any("UNPROVEN" in record.message for record in caplog.records)


@pytest.mark.asyncio
async def test_a_bug_in_the_check_is_reported_as_ours_not_as_an_outage():
    """A resolver regression must not hide as a canton that happens to be down.

    Collapsing both into `source_unreachable` — which never fails and never logs
    — would render the check permanently inert with zero signal.
    """

    def explode(_body):
        raise AttributeError("regression in the resolver")

    import platform_control.services.lexfind_api_provider as module

    original = module.source_link_candidates
    module.source_link_candidates = explode
    try:
        client = _ScriptedClient(canton={_ZH_ERLASS_URL: (b"<html>page</html>", "text/html")})
        result = await verify_mirror_fidelity(
            client, original_url=_ZH_ERLASS_URL, mirrored_body=_PDF
        )
    finally:
        module.source_link_candidates = original

    assert result.status == "check_error"
    assert result.diverged is False
    assert "AttributeError" in result.detail


# --------------------------------------------------------------------------
# The resolver is a verifier, not a crawler — and not a coin flip (#731)
# --------------------------------------------------------------------------


def test_a_document_link_outranks_an_unrelated_js_redirect():
    """Ordering by TARGET, not by markup shape.

    A `window.location.href = …` pattern searched over the whole page wins
    globally, so a cookie banner or language switch on a modern cantonal page
    would be followed instead of the document — and, with no alternatives, the
    run recorded `source_document_not_found` and said nothing.
    """
    page = (
        b"<html><head><script>function accept(){window.location.href='/cookies-ok';}"
        b"</script></head><body><a href='" + _ZH_FILE_URL.encode() + b"'>Erlasstext</a>"
        b"</body></html>"
    )
    candidates = source_link_candidates(page)

    assert candidates[0] == _ZH_FILE_URL
    assert "/cookies-ok" in candidates  # kept as a fallback, just not first


def test_candidates_are_capped_so_the_verifier_cannot_become_a_crawler():
    page = (
        b"<html>"
        + b"".join(f"<a href='/doc{i}.pdf'>x</a>".encode() for i in range(20))
        + b"</html>"
    )

    assert len(source_link_candidates(page)) <= 3


@pytest.mark.asyncio
async def test_a_dead_end_candidate_costs_a_request_not_the_answer():
    """No backtracking used to burn the whole budget on the first wrong guess."""
    decoy = "https://www.zh.ch/decoy.pdf"
    client = _ScriptedClient(
        canton={
            _ZH_ERLASS_URL: (
                b"<html><a href='" + decoy.encode() + b"'>a</a>"
                b"<a href='" + _ZH_FILE_URL.encode() + b"'>b</a></html>",
                "text/html",
            ),
            decoy: (b"<html>not a document</html>", "text/html"),
            _ZH_FILE_URL: (_PDF, "application/pdf"),
        }
    )
    result = await verify_mirror_fidelity(client, original_url=_ZH_ERLASS_URL, mirrored_body=_PDF)

    assert result.status == "identical"
    assert result.source_document_url == _ZH_FILE_URL


# --------------------------------------------------------------------------
# Politeness is not configurable away (#797)
# --------------------------------------------------------------------------


@pytest.mark.asyncio
async def test_the_pace_is_applied_before_every_canton_request(provider, monkeypatch):
    """It used to sleep between sampled DOCUMENTS.

    At the shipped default of one document that meant the delay never ran at all,
    while the resolver made up to three back-to-back requests at the canton.
    """
    slept: list[float] = []

    async def fake_sleep(seconds):
        slept.append(seconds)

    monkeypatch.setattr(asyncio, "sleep", fake_sleep)

    stub_url = "https://www.notes.zh.ch/appl/zhlex_r.nsf/OpenAttachment/$File/554.5.pdf"
    # Every erlass page in the fixture leads down the same three-request chain,
    # so the assertion does not depend on which document the seeded sample draws.
    canton = {
        stub_url: (_ZH_STUB, "text/html"),
        _ZH_FILE_URL: (_PDF, "application/pdf"),
    }
    for tol in _FIXTURE["texts_of_law_with_matches"]:
        for entry in tol["dta_urls"]:
            canton[entry["original_url"]] = (
                b"<html><a href='" + stub_url.encode() + b"'>x</a></html>",
                "text/html",
            )
    monkeypatch.setattr(
        "platform_control.services.lexfind_api_provider.httpx.AsyncClient",
        _client_factory(canton=canton),
    )
    await provider.start_run(
        SimpleNamespace(),
        SimpleNamespace(
            acquisition_spec={
                "search_text": "554",
                "entity_ids": [26],
                "mirror_spot_check_delay_seconds": 2.5,
            }
        ),
        _run(),
    )

    # Three requests to the canton at the default sample of one document: the
    # first is free, the next two are paced.
    assert slept == [2.5, 2.5]


@pytest.mark.asyncio
async def test_the_sample_size_cannot_be_configured_past_its_cap(provider, monkeypatch):
    """`{"sample": 5000, "delay": 0}` is a plausible typo, not a licence."""
    monkeypatch.setattr(
        "platform_control.services.lexfind_api_provider.httpx.AsyncClient",
        _client_factory(canton={_ZH_ERLASS_URL: (_PDF, "application/pdf")}),
    )
    result = await provider.start_run(
        SimpleNamespace(),
        _source_version(
            search_text="554",
            entity_ids=[26],
            mirror_spot_check_sample=5000,
            mirror_spot_check_delay_seconds=0,
        ),
        _run(),
    )

    # Capped at 5, then bounded again by the four documents actually captured.
    assert result.response_payload["mirror_fidelity"]["sampled"] == 4


@pytest.mark.asyncio
async def test_a_malformed_knob_is_a_named_refusal_not_a_raw_valueerror(provider, monkeypatch):
    monkeypatch.setattr(
        "platform_control.services.lexfind_api_provider.httpx.AsyncClient", _client_factory()
    )
    result = await provider.start_run(
        SimpleNamespace(),
        _source_version(search_text="554", entity_ids=[26], mirror_spot_check_sample="lots"),
        _run(),
    )

    assert result.inline_resources == []
    assert "acquisition_spec" in result.inline_failure_reason
    assert "'lots'" in result.inline_failure_reason


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


# --------------------------------------------------------------------------
# Document identity — one law, one document, across versions (#850)
# --------------------------------------------------------------------------


def _fixture_with_version(original_url: str) -> dict:
    """The captured payload with 554.51's canton URL swapped for another version's.

    The canton path encodes both dates — `erlass-554_51-<enacted>-<in_force>-<seq>.html`
    — so this is exactly what the payload looks like after ZH publishes a revision. The
    text-of-law id (22888) does not move, because the law did not become another law.
    """
    page = copy.deepcopy(_FIXTURE)
    record = next(
        t for t in page["texts_of_law_with_matches"] if t["systematic_number"] == "554.51"
    )
    record["dta_urls"][0]["original_url"] = original_url
    return page


_CANTON_V1 = (
    "https://www.zh.ch/de/politik-staat/gesetze-beschluesse/gesetzessammlung/zhlex-ls/"
    "erlass-554_51-2009_11_25-2010_01_01-129.html"
)
_CANTON_V2 = (
    "https://www.zh.ch/de/politik-staat/gesetze-beschluesse/gesetzessammlung/zhlex-ls/"
    "erlass-554_51-2009_11_25-2025_06_01-142.html"
)


async def _capture_hundeverordnung(provider, monkeypatch, page):
    monkeypatch.setattr(
        "platform_control.services.lexfind_api_provider.httpx.AsyncClient",
        _client_factory(page=page),
    )
    result = await provider.start_run(
        SimpleNamespace(),
        _source_version(search_text="554", entity_ids=[26]),
        _run(),
    )
    return next(r for r in result.inline_resources if r.title == "Hundeverordnung")


@pytest.mark.asyncio
async def test_two_versions_of_one_law_acquire_to_one_document_identity(provider, monkeypatch):
    """The #850 defect, end to end through normalization.

    ZH revising 554.51 changes `original_url` — which this provider sets as `source_url`,
    because provenance must keep pointing at the canton. Identity must NOT follow it:
    under the old global `source_url`-first rule these two captures derive two
    `document_id`s for one law and accumulate as separate searchable copies (#652/#806).
    """
    v1 = await _capture_hundeverordnung(provider, monkeypatch, _fixture_with_version(_CANTON_V1))
    v2 = await _capture_hundeverordnung(provider, monkeypatch, _fixture_with_version(_CANTON_V2))

    # The precondition that makes the assertion below non-vacuous: the URL the old
    # rule keyed on genuinely moved between the two acquisitions.
    assert v1.source_url == _CANTON_V1
    assert v2.source_url == _CANTON_V2
    assert v1.source_url != v2.source_url

    assert v1.identity_locator == v2.identity_locator == "https://www.lexfind.ch/tol/22888/de"

    # And it survives into the metadata `upstream_locator` actually reads.
    ((raw_v1, _),) = ArtifactPipeline().normalize(run_id="run_v1", resources=[v1])
    ((raw_v2, _),) = ArtifactPipeline().normalize(run_id="run_v2", resources=[v2])
    assert upstream_locator(raw_v1.metadata) == upstream_locator(raw_v2.metadata)
    # No version date leaked into identity.
    assert "2010_01_01" not in upstream_locator(raw_v1.metadata)
    assert "2025_06_01" not in upstream_locator(raw_v2.metadata)


@pytest.mark.asyncio
async def test_identity_is_the_text_of_law_id_not_a_published_version_path(provider, monkeypatch):
    """`/tolv/` is LexFind's per-VERSION path and must never be the identity.

    `matches[].dtah_urls` carries `/tolv/253109/de` for this very record, so deriving
    identity from a published URL rather than from `tol_id` is one upstream change away
    from being version-scoped again.
    """
    resource = await _capture_hundeverordnung(provider, monkeypatch, copy.deepcopy(_FIXTURE))

    assert resource.identity_locator == "https://www.lexfind.ch/tol/22888/de"
    assert "/tolv/" not in resource.identity_locator


@pytest.mark.asyncio
async def test_two_different_laws_do_not_collide_onto_one_identity(provider, monkeypatch):
    """The opposite failure: identity must still separate distinct acts."""
    monkeypatch.setattr(
        "platform_control.services.lexfind_api_provider.httpx.AsyncClient", _client_factory()
    )
    result = await provider.start_run(
        SimpleNamespace(),
        _source_version(search_text="554", entity_ids=[26]),
        _run(),
    )
    locators = [r.identity_locator for r in result.inline_resources]

    assert len(result.inline_resources) == 4
    assert len(set(locators)) == 4
