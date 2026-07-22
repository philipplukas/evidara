"""Fixture-backed tests for the LexFind provider (#731).

No network. The capture path these exercise is verified live in #716 (a
md5-identical mirror of the canton's own PDF); the discovery payload is not, and
is asserted here only for shape, not for correctness against the live contract.

The temporal assertions are the load-bearing ones. LexFind is preferred for this
rung because it models repeal separately from consolidation date, which is the
trap #661 found in Fedlex: a work whose newest consolidation is open-ended while
its status is "No longer in force" reads as current if you trust dates alone.
"""

from __future__ import annotations

from types import SimpleNamespace

import httpx
import pytest

from platform_control.services.lexfind_api_provider import (
    LexFindApiProvider,
    is_in_force,
    temporal_metadata,
)

# A structurally honest PDF: real signature, comfortably over the size floor.
_PDF = b"%PDF-1.7\n" + b"1 0 obj\n<< /Type /Catalog >>\nendobj\n" * 120 + b"%%EOF\n"

# #716, reproduced: 200 OK carrying a redirect stub where a PDF was expected.
_STUB = (
    b"<html><head><script>window.location.href='/OpenAttachment?id=1';"
    b"</script></head><body>Redirecting...</body></html>"
)

_HUNDEGESETZ = {
    "text_of_law_id": 22871,
    "title": "Hundegesetz",
    "entity_id": 26,
    "original_url": "https://www.zh.ch/erlass/554.5",
    "version_active_since": "2010-01-01",
    "version_inactive_since": None,
    "is_active": True,
}


def _source_version(**spec):
    return SimpleNamespace(acquisition_spec=spec)


def _run(run_id="run_test"):
    return SimpleNamespace(run_id=run_id, scope={})


class _ScriptedClient:
    """Minimal httpx.AsyncClient stand-in driven by a URL->payload map."""

    def __init__(self, routes, *args, **kwargs):
        del args, kwargs
        self._routes = routes
        self.requests: list[str] = []

    async def __aenter__(self):
        return self

    async def __aexit__(self, exc_type, exc, tb):
        del exc_type, exc, tb

    def _respond(self, url):
        self.requests.append(url)
        entry = self._routes.get(url)
        request = httpx.Request("GET", f"https://www.lexfind.ch{url}")
        if entry is None:
            return httpx.Response(404, request=request)
        if isinstance(entry, bytes):
            return httpx.Response(
                200, content=entry, headers={"content-type": "application/pdf"}, request=request
            )
        return httpx.Response(200, json=entry, request=request)

    async def get(self, url, *, params=None):
        del params
        return self._respond(url)

    async def post(self, url, *, json=None):
        del json
        return self._respond(url)


def _routes(*, pdf=_PDF, record=None, results=None):
    record = record if record is not None else _HUNDEGESETZ
    results = results if results is not None else [{"text_of_law_id": 22871}]
    return {
        "/api/frontend/v1/de/fulltext-search": {"id": 7, "session_id": "s-1"},
        "/api/frontend/v1/de/fulltext-search/7": {"results": results},
        "/api/frontend/v1/de/texts-of-law/22871": record,
        "/tol/22871/de": pdf,
    }


@pytest.fixture
def provider():
    return LexFindApiProvider()


# --------------------------------------------------------------------------
# Temporal validity — the #661 trap
# --------------------------------------------------------------------------


def test_active_law_maps_its_in_force_start():
    meta = temporal_metadata(_HUNDEGESETZ)
    assert meta["in_force_from"] == "2010-01-01"
    assert "in_force_until" not in meta


def test_repealed_law_carries_its_end_date():
    meta = temporal_metadata(
        {**_HUNDEGESETZ, "version_inactive_since": "2020-06-30", "is_active": False}
    )
    assert meta["in_force_until"] == "2020-06-30"
    assert meta["amendment_relation"] == "repealed_by"


def test_repeal_without_an_end_date_is_recorded_without_inventing_one():
    """We know it is repealed; we do not know when. Those are different facts.

    Collapsing them is the #661 failure in the opposite direction -- fabricating
    a boundary is exactly what ADR-0033 exists to prevent.
    """
    meta = temporal_metadata({**_HUNDEGESETZ, "version_inactive_since": None, "is_active": False})
    assert meta["amendment_relation"] == "repealed_by"
    assert "in_force_until" not in meta


def test_unknown_dates_are_absent_not_defaulted():
    meta = temporal_metadata({"title": "x"})
    assert meta == {}


def test_repealed_law_is_not_reported_in_force_despite_an_open_window():
    """The #661 trap, asserted directly.

    An open-ended newest version plus a past start date reads as "current" to any
    date-only reading. `is_active: False` must win.
    """
    record = {**_HUNDEGESETZ, "version_inactive_since": None, "is_active": False}
    assert is_in_force(record, as_of="2026-07-22") is False


def test_active_law_inside_its_window_is_in_force():
    assert is_in_force(_HUNDEGESETZ, as_of="2026-07-22") is True


def test_law_before_its_start_is_not_yet_in_force():
    assert is_in_force(_HUNDEGESETZ, as_of="2009-12-31") is False


def test_end_date_is_exclusive():
    record = {**_HUNDEGESETZ, "version_inactive_since": "2020-06-30"}
    assert is_in_force(record, as_of="2020-06-29") is True
    assert is_in_force(record, as_of="2020-06-30") is False


def test_missing_start_date_is_unknown_not_false():
    """Three-valued: absence of evidence is not evidence of absence."""
    assert is_in_force({"title": "x"}) is None


# --------------------------------------------------------------------------
# Capture, and the guards
# --------------------------------------------------------------------------


@pytest.mark.asyncio
async def test_capture_emits_a_binary_resource_with_provenance(provider, monkeypatch):
    monkeypatch.setattr(
        "platform_control.services.lexfind_api_provider.httpx.AsyncClient",
        lambda *a, **k: _ScriptedClient(_routes(), *a, **k),
    )
    result = await provider.start_run(SimpleNamespace(), _source_version(entity_ids=[26]), _run())
    assert len(result.inline_resources) == 1
    resource = result.inline_resources[0]
    assert resource.is_binary
    assert resource.content_type == "application/pdf"
    assert resource.title == "Hundegesetz"
    # The mirror must not become the citation.
    assert resource.metadata["original_url"] == "https://www.zh.ch/erlass/554.5"
    assert resource.source_url == "https://www.zh.ch/erlass/554.5"
    assert resource.metadata["in_force_from"] == "2010-01-01"
    assert resource.metadata["in_force"] is True


@pytest.mark.asyncio
async def test_716_stub_is_refused_and_recorded(provider, monkeypatch):
    """A 200 carrying a redirect stub must not become a captured statute."""
    monkeypatch.setattr(
        "platform_control.services.lexfind_api_provider.httpx.AsyncClient",
        lambda *a, **k: _ScriptedClient(_routes(pdf=_STUB), *a, **k),
    )
    result = await provider.start_run(SimpleNamespace(), _source_version(entity_ids=[26]), _run())
    assert result.inline_resources == []
    skipped = result.response_payload["skipped"]
    assert len(skipped) == 1
    assert skipped[0]["reason"] == "html_where_binary_expected"
    assert skipped[0]["tol_id"] == 22871


@pytest.mark.asyncio
async def test_undersized_pdf_is_refused(provider, monkeypatch):
    monkeypatch.setattr(
        "platform_control.services.lexfind_api_provider.httpx.AsyncClient",
        lambda *a, **k: _ScriptedClient(_routes(pdf=b"%PDF-1.7\n%%EOF\n"), *a, **k),
    )
    result = await provider.start_run(
        SimpleNamespace(), _source_version(entity_ids=[26], min_pdf_bytes=5_000), _run()
    )
    assert result.inline_resources == []
    assert result.response_payload["skipped"][0]["reason"] == "below_size_floor"


@pytest.mark.asyncio
async def test_binary_abstention_of_the_content_gate_is_recorded_not_implied(provider, monkeypatch):
    """content_gate abstains on application/pdf; the evidence must say so.

    Silence would read as "assessed and passed". ADR-0047 turns on this gap being
    visible.
    """
    monkeypatch.setattr(
        "platform_control.services.lexfind_api_provider.httpx.AsyncClient",
        lambda *a, **k: _ScriptedClient(_routes(), *a, **k),
    )
    result = await provider.start_run(SimpleNamespace(), _source_version(entity_ids=[26]), _run())
    meta = result.inline_resources[0].metadata
    assert meta["legal_text_assessment"] == "abstained_binary_manifestation"


@pytest.mark.asyncio
async def test_max_documents_bounds_the_run(provider, monkeypatch):
    routes = _routes(results=[{"text_of_law_id": 22871}, {"text_of_law_id": 22888}])
    monkeypatch.setattr(
        "platform_control.services.lexfind_api_provider.httpx.AsyncClient",
        lambda *a, **k: _ScriptedClient(routes, *a, **k),
    )
    result = await provider.start_run(
        SimpleNamespace(), _source_version(entity_ids=[26], max_documents=1), _run()
    )
    assert len(result.inline_resources) == 1


# --------------------------------------------------------------------------
# Readiness and plan honesty
# --------------------------------------------------------------------------


def test_readiness_admits_only_an_acceptance_run(provider):
    """Implemented and tested, but no operator evidence yet (ADR-0030)."""
    assert provider.readiness.value == "awaiting_evidence"


def test_plan_declares_the_discovery_payload_unverified(provider):
    """An operator must see this before dispatching, not after."""
    plan = provider.plan(SimpleNamespace(), _source_version(entity_ids=[26]))
    assert any("UNVERIFIED" in note for note in plan.notes)
    assert plan.raw["search_payload_verified"] is False


def test_plan_warns_when_no_entity_is_scoped(provider):
    plan = provider.plan(SimpleNamespace(), _source_version())
    assert any("entity_ids" in note for note in plan.notes)


def test_plan_makes_no_network_calls(provider):
    """`pc source plan` must stay free."""
    plan = provider.plan(SimpleNamespace(), _source_version(entity_ids=[26]))
    assert plan.provider == "lexfind_api"
    assert plan.max_discovery_depth == 0
