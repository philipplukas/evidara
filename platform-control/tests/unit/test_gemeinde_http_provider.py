"""Unit tests for the CH communal (Gemeinde) HTTP provider — #584.

WHY THESE TESTS EXIST:
- The AS landing-page parser is the real, working half of this scaffold. It
  runs against a fixture captured verbatim from the live City of Zurich page,
  so it proves we can actually locate a communal ordinance and read its
  lifecycle metadata — including `in_force_until`, the repeal date ADR-0033
  records as missing from the corpus.
- The REFUSAL is the load-bearing behaviour. Zurich's ordinance is PDF-only, and
  the provider must NOT fall back to emitting the metadata landing page in place
  of the ordinance. Indexing a metadata stub as if it were the law is the "demo
  that lies convincingly" failure ADR-0033 exists to prevent — so it is asserted
  here. (The PDF itself is carried as `body_bytes` since #590; the refusal guards
  the landing-page substitution, not a missing binary capability.)
- Host allow-list + BFS validation: prevents an operator from pointing a
  commune template at an arbitrary host.
- Scaffold guard: `live_ready is False` keeps the ADR-0030 two-key lock shut.
"""

from __future__ import annotations

from pathlib import Path
from types import SimpleNamespace

import httpx
import pytest

from acquisition_core.providers import (
    AcquisitionReadiness,
    ProviderNotLiveReadyError,
    ensure_launchable,
    provider_readiness,
)
from platform_control.errors import ProviderConfigurationError
from platform_control.services.gemeinde_http_provider import (
    GemeindeHttpProvider,
    load_communal_portals,
    parse_amtliche_sammlung_page,
)

FIXTURE = (
    Path(__file__).resolve().parents[1]
    / "fixtures"
    / "gemeinde_http"
    / "stadt_zuerich_as_554_510.html"
)
LANDING_URL = (
    "https://www.stadt-zuerich.ch/de/politik-und-verwaltung/politik-und-recht"
    "/amtliche-sammlung/5/554/510.html"
)


def _fixture_html() -> str:
    return FIXTURE.read_text(encoding="utf-8")


def test_supported_portals_are_loaded_from_config() -> None:
    # #632: the BFS -> host allow-list is data (communal_portals.yaml), not a
    # Python ClassVar. Registering commune #2 is an edit to that file, not code.
    portals = GemeindeHttpProvider().supported_portals
    assert portals is load_communal_portals()  # same cached config object
    assert 261 in portals
    assert portals[261].host == "www.stadt-zuerich.ch"
    assert portals[261].canton_jurisdiction_id == "jur_ch_zh"


# ─── Builders for synthetic landing pages ───────────────────────
# The live page HTML-escapes a JSON payload into a web-component attribute, and
# escapes the inner <a href> a second time. These builders reproduce that shape
# so synthetic cases exercise the same parse path as the captured fixture.


def _row(field: str, value: str) -> str:
    return f"[{{&#34;id&#34;:&#34;{field}&#34;,&#34;value&#34;:&#34;{value}&#34;}}]"


def _link(href: str) -> str:
    return f"&lt;a href=\\&#34;{href}\\&#34;>text&lt;/a>"


def _landing_page(*, title: str, rows: list[str]) -> str:
    payload = ",".join(rows)
    return (
        f"<html><head><title>{title} | Stadt Zürich</title></head><body>"
        f'<x-table rows="[{payload}]"></x-table></body></html>'
    )


# A minimal well-formed PDF. Content does not matter here — that the *bytes* survive
# acquisition unmodified does.
_PDF_BYTES = b"%PDF-1.4\n1 0 obj\n<< /Type /Catalog >>\nendobj\ntrailer\n<< /Root 1 0 R >>\n%%EOF\n"


class _FakeClient:
    def __init__(self, responses: dict[str, tuple[int, str, dict[str, str]]]) -> None:
        self.responses = responses
        self.calls: list[str] = []

    async def __aenter__(self) -> _FakeClient:
        return self

    async def __aexit__(self, exc_type, exc, tb) -> None:
        del exc_type, exc, tb

    async def get(self, url: str):
        self.calls.append(url)
        for prefix, (status, body, headers) in self.responses.items():
            if url.startswith(prefix):
                request = httpx.Request("GET", url)
                # A PDF manifestation is served as bytes; decoding it here would hide
                # the very corruption the binary path exists to prevent.
                if isinstance(body, bytes):
                    return httpx.Response(status, content=body, headers=headers, request=request)
                return httpx.Response(status, text=body, headers=headers, request=request)
        raise AssertionError(f"unexpected URL: {url}")


def _install_fake_client(
    monkeypatch: pytest.MonkeyPatch,
    responses: dict[str, tuple[int, str, dict[str, str]]],
) -> _FakeClient:
    captured = _FakeClient(responses)

    def factory(*args, **kwargs):
        del args, kwargs
        return captured

    monkeypatch.setattr(httpx, "AsyncClient", factory)
    return captured


# ─── The parser (the working half) ──────────────────────────────


def test_parses_real_amtliche_sammlung_landing_page() -> None:
    record = parse_amtliche_sammlung_page(_fixture_html(), page_url=LANDING_URL)

    assert record["as_number"] == "554.510"
    assert record["title"] == "Vollzugsvorschriften zum Hundegesetz"
    assert record["decided_on"] == "2017-05-31"
    assert record["in_force_from"] == "2017-09-01"
    # Empty on the live page = still in force. This is exactly the repeal/until
    # date ADR-0033 says the corpus cannot express; the municipal layer
    # publishes it, so the provider must surface it rather than drop it.
    assert record["in_force_until"] is None

    # The operative text is a PDF — there is no HTML manifestation. The href on
    # the live page contains literal spaces; urljoin must still resolve it.
    assert record["document_content_type"] == "application/pdf"
    assert record["document_url"].startswith("https://www.stadt-zuerich.ch/dam/")
    assert record["document_url"].endswith(".pdf")


def test_parser_reads_a_repeal_date_when_the_enactment_is_superseded() -> None:
    # Superseded versions carry a non-empty Ausserkrafttreten. Synthesised from
    # the same field ids the live page uses.
    html = _landing_page(
        title="Alt",
        rows=[
            _row("inkrafttretendatum", "01.07.2015"),
            _row("ausserkrafttretendatum", "31.08.2017"),
            _row("rechtstexte", _link("/dam/old.pdf")),
        ],
    )
    record = parse_amtliche_sammlung_page(html, page_url=LANDING_URL)
    assert record["in_force_from"] == "2015-07-01"
    assert record["in_force_until"] == "2017-08-31"


# ─── The refusal (the load-bearing behaviour) ───────────────────


@pytest.mark.asyncio
async def test_pdf_only_ordinance_is_emitted_as_a_binary_manifestation(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    """The Zurich case: PDF-only, and since #590 that is carried, not refused.

    The ordinance travels as raw bytes (`body_bytes`); decoding it would corrupt the
    PDF before it ever reached the normaliser. It must still never emit the metadata
    landing page as a stand-in for the ordinance.
    """
    _install_fake_client(
        monkeypatch,
        {
            "https://www.stadt-zuerich.ch/de/": (
                200,
                _fixture_html(),
                {"content-type": "text/html; charset=utf-8"},
            ),
            # The operative text the landing page links to (Zürich publishes PDF).
            "https://www.stadt-zuerich.ch/dam/": (
                200,
                _PDF_BYTES,
                {"content-type": "application/pdf"},
            ),
        },
    )
    provider = GemeindeHttpProvider()
    source_version = SimpleNamespace(acquisition_spec={"bfs_number": 261, "seed_url": LANDING_URL})
    result = await provider.start_run(
        SimpleNamespace(),
        source_version,
        SimpleNamespace(run_id="run_zh_261_1"),
    )

    # The ordinance itself is acquired — nothing skipped, nothing substituted.
    assert result.response_payload["captured"] == 1
    assert result.response_payload["skipped"] == 0
    assert result.inline_failure_reason is None

    resource = result.inline_resources[0]
    # Binary: bytes, not text. A decoded PDF is a corrupted PDF.
    assert resource.is_binary
    assert resource.body is None
    assert resource.body_bytes == _PDF_BYTES
    assert resource.raw_bytes.startswith(b"%PDF-")
    assert resource.content_type == "application/pdf"

    # It is the operative text, not the landing page it was discovered through.
    assert resource.source_url.endswith(".pdf")
    assert resource.metadata["as_number"] == "554.510"
    assert resource.metadata["in_force_from"] == "2017-09-01"


@pytest.mark.asyncio
async def test_html_manifestation_would_be_acquired_normally(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    """A commune publishing HTML law acquires fine — the block is PDF, not municipal.

    Guards against the scaffold being written as an unconditional failure: the
    provider is a real acquisition path that is blocked only on binary bodies.
    """
    landing = _landing_page(
        title="Hundereglement",
        rows=[
            _row("ASZ", "554.510"),
            _row("inkrafttretendatum", "01.09.2017"),
            _row("rechtstexte", _link("/recht/hunde.html")),
        ],
    )
    _install_fake_client(
        monkeypatch,
        {
            "https://www.stadt-zuerich.ch/de/": (
                200,
                landing,
                {"content-type": "text/html; charset=utf-8"},
            ),
            "https://www.stadt-zuerich.ch/recht/hunde.html": (
                200,
                "<html><body>Art. 1 Der Stadtrat ...</body></html>",
                {"content-type": "text/html; charset=utf-8"},
            ),
        },
    )
    provider = GemeindeHttpProvider()
    result = await provider.start_run(
        SimpleNamespace(),
        SimpleNamespace(acquisition_spec={"bfs_number": 261, "seed_url": LANDING_URL}),
        SimpleNamespace(run_id="run_zh_261_2"),
    )
    assert result.inline_failure_reason is None
    assert result.response_payload["captured"] == 1
    resource = result.inline_resources[0]
    assert "Art. 1" in resource.body
    # The municipal document carries its level and links up to its canton (#583).
    assert resource.metadata["level"] == "municipal"
    assert resource.metadata["jurisdiction_id"] == "jur_ch_gemeinde_261"
    assert resource.metadata["parent_jurisdiction_id"] == "jur_ch_zh"
    assert resource.metadata["bfs_number"] == 261


# ─── Config validation / safety ─────────────────────────────────


@pytest.mark.asyncio
async def test_rejects_seed_from_foreign_host(monkeypatch: pytest.MonkeyPatch) -> None:
    _install_fake_client(monkeypatch, {})
    provider = GemeindeHttpProvider()
    with pytest.raises(ProviderConfigurationError, match="host must match"):
        await provider.start_run(
            SimpleNamespace(),
            SimpleNamespace(
                acquisition_spec={
                    "bfs_number": 261,
                    "seed_url": "https://attacker.example.com/exfil",
                }
            ),
            SimpleNamespace(run_id="run_x"),
        )


@pytest.mark.asyncio
async def test_rejects_unknown_bfs_number() -> None:
    provider = GemeindeHttpProvider()
    # 2,110 communes are seeded as jurisdictions; only allow-listed ones have a
    # verified portal. An unlisted commune must fail loudly, not guess a host.
    with pytest.raises(ProviderConfigurationError, match="no supported portal"):
        await provider.start_run(
            SimpleNamespace(),
            SimpleNamespace(
                acquisition_spec={"bfs_number": 1, "seed_url": "https://whatever.example/"}
            ),
            SimpleNamespace(run_id="run_x"),
        )


@pytest.mark.asyncio
async def test_requires_bfs_number() -> None:
    provider = GemeindeHttpProvider()
    with pytest.raises(ProviderConfigurationError, match="bfs_number"):
        await provider.start_run(
            SimpleNamespace(),
            SimpleNamespace(acquisition_spec={"seed_url": LANDING_URL}),
            SimpleNamespace(run_id="run_x"),
        )


@pytest.mark.asyncio
async def test_requires_seed_urls() -> None:
    provider = GemeindeHttpProvider()
    with pytest.raises(ProviderConfigurationError, match="seed_url"):
        await provider.start_run(
            SimpleNamespace(),
            SimpleNamespace(acquisition_spec={"bfs_number": 261}),
            SimpleNamespace(run_id="run_x"),
        )


def test_plan_reports_scaffold_status_without_network_io() -> None:
    provider = GemeindeHttpProvider()
    plan = provider.plan(
        SimpleNamespace(),
        SimpleNamespace(acquisition_spec={"bfs_number": 261, "seed_url": LANDING_URL}),
    )
    assert plan.provider == "gemeinde_http"
    assert plan.seed_urls == [LANDING_URL]
    assert any("jur_ch_gemeinde_261" in note for note in plan.notes)
    assert any("readiness=awaiting_evidence" in note for note in plan.notes)


def test_gemeinde_http_provider_awaits_evidence_rather_than_being_a_scaffold() -> None:
    # NOT a scaffold, and the distinction is the point (#743). Acquisition (#590)
    # and PDF normalisation (#650, ADR-0041) both landed and are verified against
    # the real AS 554.510 PDF. The code key is shut on the one remaining ADR-0030
    # requirement — acceptance-run evidence — which an operator can capture
    # themselves. Reporting this as a scaffold sent operators to an engineer to
    # build something that already existed.
    assert provider_readiness(GemeindeHttpProvider) is AcquisitionReadiness.AWAITING_EVIDENCE


def test_gemeinde_http_admits_an_acceptance_run_but_not_a_production_one() -> None:
    # The deadlock this state exists to break: evidence needs a live run, the
    # live run needed the code key, and the code key needed the evidence.
    ensure_launchable(GemeindeHttpProvider, for_acceptance=True)

    with pytest.raises(ProviderNotLiveReadyError) as excinfo:
        ensure_launchable(GemeindeHttpProvider)
    # The refusal must point at the loop, not at engineering.
    assert "acceptance run" in str(excinfo.value)
    assert "does not need an engineer" in str(excinfo.value)
