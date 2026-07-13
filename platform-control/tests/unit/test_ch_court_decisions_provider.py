from __future__ import annotations

import re
from pathlib import Path
from types import SimpleNamespace

import httpx
import pytest

from platform_control.services.ch_court_decisions_provider import (
    _DEFAULT_ALLOWED_HOSTS,
    _DEFAULT_LINK_PATTERN,
    ChCourtDecisionsProvider,
    _extract_citation_metadata,
    _extract_links,
    _extract_title,
)

_FIXTURES_DIR = Path(__file__).resolve().parents[1] / "fixtures" / "ch_court_decisions"

_INDEX_URL = "https://www.bger.ch/decisions/index.html"
_DECISION_URL = "https://www.bger.ch/decisions/1C_123_2024.html"
_DISALLOWED_URL = "https://evil.example.com/1C_9/2024.html"

_INDEX_HTML = """
<html><head><title>Entscheide</title></head><body>
  <ul>
    <li><a href="/decisions/1C_123_2024.html">1C_123/2024</a></li>
    <li><a href="https://evil.example.com/leak.html">off-host</a></li>
    <li><a href="/about">not a decision</a></li>
  </ul>
</body></html>
"""

_DECISION_HTML = """
<html><head><title>Urteil 1C_123/2024 vom 12. März 2024</title></head><body>
  <h1>Bundesgericht</h1>
  <p>Urteil vom 12. März 2024 (1C_123/2024)</p>
  <p>ECLI:CH:BGER:2024:1C_123.2024.1</p>
  <p>Publiziert als BGE 150 II 1.</p>
  <p>Erwägungen ...</p>
</body></html>
"""


class _FakeCourtClient:
    """Routes index/decision URLs to fixtures; everything else times out."""

    def __init__(self, *args, **kwargs) -> None:
        del args, kwargs

    async def __aenter__(self) -> _FakeCourtClient:
        return self

    async def __aexit__(self, exc_type, exc, tb) -> None:
        del exc_type, exc, tb

    async def get(self, url: str, **kwargs):
        del kwargs
        request = httpx.Request("GET", url)
        if url == _INDEX_URL:
            return httpx.Response(
                200, html=_INDEX_HTML, headers={"content-type": "text/html"}, request=request
            )
        if url == _DECISION_URL:
            return httpx.Response(
                200, html=_DECISION_HTML, headers={"content-type": "text/html"}, request=request
            )
        raise httpx.ReadTimeout("timed out", request=request)


def _source_version(acquisition_spec: dict) -> SimpleNamespace:
    return SimpleNamespace(acquisition_spec=acquisition_spec)


@pytest.mark.asyncio
async def test_discovers_and_shapes_decision_with_citation_metadata(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    monkeypatch.setattr(httpx, "AsyncClient", _FakeCourtClient)
    provider = ChCourtDecisionsProvider()

    result = await provider.start_run(
        SimpleNamespace(),
        _source_version({"provider": "ch_court_decisions", "index_urls": [_INDEX_URL]}),
        SimpleNamespace(run_id="run_ch_court_1", scope=None),
    )

    assert result.provider == "ch_court_decisions"
    assert result.response_payload["captured"] == 1
    # Only the on-host decision link was discovered (off-host + non-decision dropped).
    assert result.response_payload["discovered"] == 1
    assert result.inline_failure_reason is None

    resource = result.inline_resources[0]
    assert resource.content_type == "text/html"
    assert resource.final_url == _DECISION_URL
    assert resource.discovery_depth == 1
    assert resource.metadata["court"] == "bger"
    assert resource.metadata["docket"] == "1C_123/2024"
    assert resource.metadata["bge_reference"] == "BGE 150 II 1"
    assert resource.metadata["ecli"] == "ECLI:CH:BGER:2024:1C_123.2024.1"
    assert resource.metadata["decision_date"] == "12. März 2024"
    assert resource.metadata["run_id"] == "run_ch_court_1"


@pytest.mark.asyncio
async def test_direct_seed_url_is_fetched(monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setattr(httpx, "AsyncClient", _FakeCourtClient)
    provider = ChCourtDecisionsProvider()

    result = await provider.start_run(
        SimpleNamespace(),
        _source_version(
            {"provider": "ch_court_decisions", "seed_url": _DECISION_URL, "court": "bger"}
        ),
        SimpleNamespace(run_id="run_ch_court_2", scope=None),
    )

    assert result.response_payload["captured"] == 1
    assert result.response_payload["discovered"] == 0
    resource = result.inline_resources[0]
    assert resource.discovery_depth == 0
    assert resource.metadata["docket"] == "1C_123/2024"


@pytest.mark.asyncio
async def test_disallowed_host_is_rejected_without_fetch(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    monkeypatch.setattr(httpx, "AsyncClient", _FakeCourtClient)
    provider = ChCourtDecisionsProvider()

    result = await provider.start_run(
        SimpleNamespace(),
        _source_version({"provider": "ch_court_decisions", "seed_urls": [_DISALLOWED_URL]}),
        SimpleNamespace(run_id="run_ch_court_3", scope=None),
    )

    assert result.response_payload["captured"] == 0
    assert result.response_payload["skipped_disallowed"] == 1
    assert result.inline_resources == []
    assert "not in allow-list" in result.response_payload["failures"][0]["error"]


@pytest.mark.asyncio
async def test_timeout_yields_failure_and_reason(monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setattr(httpx, "AsyncClient", _FakeCourtClient)
    provider = ChCourtDecisionsProvider()

    result = await provider.start_run(
        SimpleNamespace(),
        _source_version(
            {
                "provider": "ch_court_decisions",
                "seed_urls": ["https://www.bger.ch/decisions/missing.html"],
                "request_timeout_seconds": 7.0,
            }
        ),
        SimpleNamespace(run_id="run_ch_court_4", scope=None),
    )

    assert result.response_payload["captured"] == 0
    assert result.response_payload["failed"] == 1
    assert "did not capture any resources" in (result.inline_failure_reason or "")
    assert "timed out after 7.0s" in result.response_payload["failures"][0]["error"]


def test_plan_reports_targets_without_network() -> None:
    provider = ChCourtDecisionsProvider()
    plan = provider.plan(
        SimpleNamespace(),
        _source_version(
            {
                "provider": "ch_court_decisions",
                "seed_urls": [_DECISION_URL],
                "index_urls": [_INDEX_URL],
                "court": "bger",
            }
        ),
    )
    assert plan.provider == "ch_court_decisions"
    assert plan.mode == "html_court_decisions"
    assert _DECISION_URL in plan.seed_urls
    assert _INDEX_URL in plan.seed_urls
    assert any("court=bger" in note for note in plan.notes)


def test_provider_is_scaffold_until_live_enablement() -> None:
    assert ChCourtDecisionsProvider.live_ready is False


# ---------------------------------------------------------------------------
# Recorded fixture ("cassette") — locks end-to-end parse behaviour for the
# eventual live BGer acceptance run. See docs/runbooks/ch-bger-live-enablement.md.
# ---------------------------------------------------------------------------

_CASSETTE_URL = "https://www.bger.ch/decisions/aza/1C_123_2024.html"
_CASSETTE_HTML = (_FIXTURES_DIR / "bger_1C_123_2024.html").read_text(encoding="utf-8")


class _CassetteClient:
    """Serves the recorded BGer decision fixture for a single seed URL."""

    def __init__(self, *args, **kwargs) -> None:
        del args, kwargs

    async def __aenter__(self) -> _CassetteClient:
        return self

    async def __aexit__(self, exc_type, exc, tb) -> None:
        del exc_type, exc, tb

    async def get(self, url: str, **kwargs):
        del kwargs
        request = httpx.Request("GET", url)
        if url == _CASSETTE_URL:
            return httpx.Response(
                200,
                html=_CASSETTE_HTML,
                headers={"content-type": "text/html; charset=utf-8"},
                request=request,
            )
        raise httpx.ReadTimeout("timed out", request=request)


@pytest.mark.asyncio
async def test_recorded_bger_cassette_shapes_one_resource(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    """The captured BGer ruling must yield exactly one fully-shaped resource.

    This is the behaviour lock for live enablement: docket, court, ECLI, BGE
    reference, decision date and title are all extracted from realistic HTML.
    """
    monkeypatch.setattr(httpx, "AsyncClient", _CassetteClient)
    provider = ChCourtDecisionsProvider()

    result = await provider.start_run(
        SimpleNamespace(),
        _source_version({"provider": "ch_court_decisions", "seed_url": _CASSETTE_URL}),
        SimpleNamespace(run_id="run_ch_court_cassette", scope=None),
    )

    assert result.response_payload["captured"] == 1
    assert result.inline_failure_reason is None

    resource = result.inline_resources[0]
    assert resource.content_type == "text/html"
    assert resource.http_status == 200
    assert resource.discovery_depth == 0
    # Title is the real <title>, with the &mdash; entity decoded.
    assert resource.title.startswith("Urteil 1C_123/2024 vom 12. März 2024")
    assert "—" in resource.title
    assert resource.metadata["court"] == "bger"
    assert resource.metadata["docket"] == "1C_123/2024"
    assert resource.metadata["bge_reference"] == "BGE 150 II 1"
    assert resource.metadata["ecli"] == "ECLI:CH:BGER:2024:1C_123.2024.1"
    assert resource.metadata["decision_date"] == "12. März 2024"
    assert resource.metadata["document_type"] == "decision"


# ---------------------------------------------------------------------------
# Multilingual / robustness hardening (targeted unit coverage).
# ---------------------------------------------------------------------------


@pytest.mark.parametrize(
    ("body", "expected"),
    [
        ("Urteil vom 12. März 2024", "12. März 2024"),  # DE
        ("arrêt du 12 mars 2024", "12 mars 2024"),  # FR (no day period)
        ("arrêt du 1er mars 2024", "1er mars 2024"),  # FR ordinal
        ("sentenza del 12 marzo 2024", "12 marzo 2024"),  # IT
        ("Décision du 3 février 2023", "3 février 2023"),  # FR accented month
    ],
)
def test_decision_date_regex_is_multilingual(body: str, expected: str) -> None:
    assert _extract_citation_metadata(body)["decision_date"] == expected


@pytest.mark.parametrize(
    ("body", "expected"),
    [
        ("Urteil 1C_123/2024", "1C_123/2024"),  # BGer chamber form
        ("Arrêt 6B_45/2023", "6B_45/2023"),  # BGer French
        ("Urteil A-1234/2024 der Abteilung I", "A-1234/2024"),  # BVGer division form
        ("Décision B-567/2023", "B-567/2023"),  # BVGer French
    ],
)
def test_docket_regex_covers_bger_and_bvger(body: str, expected: str) -> None:
    assert _extract_citation_metadata(body)["docket"] == expected


@pytest.mark.parametrize(
    ("body", "expected"),
    [
        ("ATF 149 III 1", "ATF 149 III 1"),  # FR reporter
        ("DTF 149 III 1", "DTF 149 III 1"),  # IT reporter
    ],
)
def test_bge_reference_regex_covers_fr_it(body: str, expected: str) -> None:
    assert _extract_citation_metadata(body)["bge_reference"] == expected


def test_title_falls_back_to_h1_when_title_empty() -> None:
    body = "<html><head><title>   </title></head><body><h1>Arrêt 6B_45/2023</h1></body></html>"
    assert _extract_title(body) == "Arrêt 6B_45/2023"


def test_title_decodes_entities_and_strips_nested_tags() -> None:
    body = "<html><head><title>Urteil &amp; <span>Beschluss</span></title></head></html>"
    assert _extract_title(body) == "Urteil & Beschluss"


def test_link_discovery_unescapes_html_entities() -> None:
    body = '<a href="/decisions/list?docid=1C_9/2024&amp;lang=de">ruling</a>'
    links = _extract_links(
        "https://www.bger.ch/",
        body,
        re.compile(_DEFAULT_LINK_PATTERN),
        _DEFAULT_ALLOWED_HOSTS,
    )
    assert links == ["https://www.bger.ch/decisions/list?docid=1C_9/2024&lang=de"]
