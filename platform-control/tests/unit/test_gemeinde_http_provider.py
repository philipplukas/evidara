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
    ensure_launchable,
    provider_readiness,
)
from platform_control.errors import ProviderConfigurationError
from platform_control.services.gemeinde_http_provider import (
    GemeindeHttpProvider,
    load_communal_portals,
    parse_amtliche_sammlung_page,
)
from platform_control.services.politeness import current_rate_limiter
from platform_control.services.robots import (
    RobotsChecker,
    RobotsContext,
    RobotsMode,
    current_robots_context,
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


# A well-formed PDF standing in for a real ordinance. Content does not matter here —
# that the *bytes* survive acquisition unmodified does — but the SIZE now does: the
# capture guard's byte floor (`_DEFAULT_MIN_BINARY_BYTES`) refuses a stub, and a
# 70-byte "PDF" is a stub by any honest reading. Padded with a comment stream so the
# fixture is a plausible one-page ordinance rather than something only a test accepts.
_PDF_BYTES = (
    b"%PDF-1.4\n1 0 obj\n<< /Type /Catalog >>\nendobj\n"
    + b"% Vollzugsvorschriften zum Hundegesetz, Art. 1 Abs. 1\n" * 24
    + b"trailer\n<< /Root 1 0 R >>\n%%EOF\n"
)
# An HTML ordinance as a commune that publishes law as HTML would serve it. The
# previous fixture ("Art. 1 Der Stadtrat ...") carried one legal-text marker and so
# scored below `content_gate`'s floor of three: it was indistinguishable from a
# navigation shell, which is the point of the gate. Real law clears the floor in its
# first two articles.
_HTML_ORDINANCE = (
    "<html><body><h1>Hundereglement</h1>"
    "<p>Art. 1 Abs. 1 Der Stadtrat regelt das Halten von Hunden.</p>"
    "<p>Art. 2 Abs. 2 Ziff. 3 Hunde sind an der Leine zu führen.</p>"
    "</body></html>"
)
# A 142-byte JavaScript redirect stub served with a 200 where a PDF was promised —
# the #716 payload, reproduced as bytes so the guard meets the real failure shape.
_REDIRECT_STUB_BYTES = (
    b'<!DOCTYPE html><html><head><meta http-equiv="refresh" content="0;'
    b'url=/login"><script>window.location="/login";</script></head>'
    b"<body></body></html>"
)


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
                _HTML_ORDINANCE,
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


# ─── The capture guard (#631/#716 at the municipal rung) ────────
#
# Mutation check for all four: delete the `check_capture(...)`/
# `assess_legal_text_density(...)` block in `gemeinde_http_provider.start_run` and the
# three refusal tests fail — the stub is captured, `captured` reads 1 and
# `inline_failure_reason` is None. The pass tests fail only if the guard is wired with
# the wrong expectation (a byte floor on HTML, a marker floor on PDF), which is the
# other way this goes wrong.


@pytest.mark.asyncio
async def test_javascript_stub_served_where_a_pdf_was_promised_is_refused(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    """#716's payload, one rung down: a `200` carrying a redirect stub, not a statute.

    The landing page's `rechtstexte` link ends in `.pdf`, so the provider's
    `content_type` is derived from the SUFFIX — a promise made by the page, not by
    the server. Nothing but the capture guard makes the server keep it. Before it was
    wired, these 142 bytes were counted in `captured` and shipped downstream as the
    Vollzugsvorschriften.
    """
    _install_fake_client(
        monkeypatch,
        {
            "https://www.stadt-zuerich.ch/de/": (
                200,
                _fixture_html(),
                {"content-type": "text/html; charset=utf-8"},
            ),
            "https://www.stadt-zuerich.ch/dam/": (
                200,
                _REDIRECT_STUB_BYTES,
                # The server declares PDF; only the bytes give it away.
                {"content-type": "application/pdf"},
            ),
        },
    )
    provider = GemeindeHttpProvider()
    result = await provider.start_run(
        SimpleNamespace(),
        SimpleNamespace(acquisition_spec={"bfs_number": 261, "seed_url": LANDING_URL}),
        SimpleNamespace(run_id="run_zh_261_stub"),
    )

    assert result.response_payload["captured"] == 0
    assert result.inline_resources == []
    skipped = result.response_payload["skipped_manifestations"]
    assert len(skipped) == 1
    # The most specific defect, not a downstream symptom: it is HTML, not a short PDF.
    assert skipped[0]["reason"] == "html_where_binary_expected"
    # The operator is sent to the portal, not to a capability gap.
    assert "capture guard refused" in result.inline_failure_reason
    assert "html_where_binary_expected" in result.inline_failure_reason


@pytest.mark.asyncio
async def test_pdf_declared_as_html_is_refused_before_the_bytes_are_read(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    """A `.pdf` link answered with `text/html` is a login wall or an error page."""
    _install_fake_client(
        monkeypatch,
        {
            "https://www.stadt-zuerich.ch/de/": (
                200,
                _fixture_html(),
                {"content-type": "text/html; charset=utf-8"},
            ),
            "https://www.stadt-zuerich.ch/dam/": (
                200,
                _PDF_BYTES,
                {"content-type": "text/html; charset=utf-8"},
            ),
        },
    )
    provider = GemeindeHttpProvider()
    result = await provider.start_run(
        SimpleNamespace(),
        SimpleNamespace(acquisition_spec={"bfs_number": 261, "seed_url": LANDING_URL}),
        SimpleNamespace(run_id="run_zh_261_ct"),
    )

    assert result.response_payload["captured"] == 0
    assert result.response_payload["skipped_manifestations"][0]["reason"] == (
        "content_type_mismatch"
    )


@pytest.mark.asyncio
async def test_html_navigation_shell_is_refused_at_the_municipal_rung(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    """#631 for communes that publish HTML: a well-formed page with no law in it.

    `check_capture` cannot see this — a nav shell is honest HTML with visible text —
    which is why both gates are wired, not one.
    """
    _install_fake_client(
        monkeypatch,
        {
            "https://www.stadt-zuerich.ch/de/": (
                200,
                _landing_page(
                    title="Hundereglement",
                    rows=[
                        _row("ASZ", "554.510"),
                        _row("rechtstexte", _link("/recht/hunde.html")),
                    ],
                ),
                {"content-type": "text/html; charset=utf-8"},
            ),
            "https://www.stadt-zuerich.ch/recht/hunde.html": (
                200,
                "<html><head><script>var nav=1;</script></head>"
                "<body><nav>Startseite Kontakt Impressum</nav></body></html>",
                {"content-type": "text/html; charset=utf-8"},
            ),
        },
    )
    provider = GemeindeHttpProvider()
    result = await provider.start_run(
        SimpleNamespace(),
        SimpleNamespace(acquisition_spec={"bfs_number": 261, "seed_url": LANDING_URL}),
        SimpleNamespace(run_id="run_zh_261_shell"),
    )

    assert result.response_payload["captured"] == 0
    skipped = result.response_payload["skipped_manifestations"][0]
    assert skipped["reason"] == "no_legal_text_markers"
    assert skipped["legal_marker_count"] == 0


@pytest.mark.asyncio
async def test_a_genuine_pdf_capture_records_the_guard_verdict_as_evidence(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    """The other half: an honest capture passes, and says so in its metadata.

    The density gate abstains on `application/pdf` and is called anyway, so the
    abstention is recorded rather than implied by its absence — the same convention
    `lexfind_api` follows. Judging a PDF's text belongs to DI (ADR-0047), and this
    provider must not grow a second opinion about it.
    """
    _install_fake_client(
        monkeypatch,
        {
            "https://www.stadt-zuerich.ch/de/": (
                200,
                _fixture_html(),
                {"content-type": "text/html; charset=utf-8"},
            ),
            "https://www.stadt-zuerich.ch/dam/": (
                200,
                _PDF_BYTES,
                {"content-type": "application/pdf"},
            ),
        },
    )
    provider = GemeindeHttpProvider()
    result = await provider.start_run(
        SimpleNamespace(),
        SimpleNamespace(acquisition_spec={"bfs_number": 261, "seed_url": LANDING_URL}),
        SimpleNamespace(run_id="run_zh_261_ok"),
    )

    assert result.response_payload["captured"] == 1
    metadata = result.inline_resources[0].metadata
    assert metadata["capture_guard"] == "passed"
    assert metadata["legal_text_assessment"] == "abstained_binary_manifestation"


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


def test_plan_reports_readiness_without_network_io() -> None:
    provider = GemeindeHttpProvider()
    plan = provider.plan(
        SimpleNamespace(),
        SimpleNamespace(acquisition_spec={"bfs_number": 261, "seed_url": LANDING_URL}),
    )
    assert plan.provider == "gemeinde_http"
    assert plan.seed_urls == [LANDING_URL]
    assert any("jur_ch_gemeinde_261" in note for note in plan.notes)
    assert any("readiness=live" in note for note in plan.notes)


def test_gemeinde_http_provider_is_live_on_captured_evidence() -> None:
    """The code key is open, and it was earned rather than asserted (#735).

    Acquisition (#590) and PDF normalisation (#650, ADR-0041) both landed, and an
    ADR-0030 acceptance run against live Zürich AS 554.510 on 2026-07-20 verified
    the result with every gate armed and `skipped_gates: []`. Evidence:
    docs/runbooks/evidence/2026-07-20-ch-gemeinde-zuerich-acceptance.md

    Roll back to SCAFFOLD, never to AWAITING_EVIDENCE — the latter is the one
    state whose acceptance runs waive the operator's config key, so it would
    re-open the route a rollback is trying to close.
    """
    assert provider_readiness(GemeindeHttpProvider) is AcquisitionReadiness.LIVE

    # Every mode now passes the code key. The config key is separate and
    # operator-owned, and the templates still ship `enabled: false`.
    ensure_launchable(GemeindeHttpProvider)
    ensure_launchable(GemeindeHttpProvider, for_acceptance=True)


# ─── Politeness (#735 review) ───────────────────────────────────
#
# `cp_ch_municipal` is the most conservative compliance tier in the repo and was
# written for this provider specifically: robots_mode=strict, a FLAT 10 rpm
# ceiling (deliberately equal to the start rate so the adaptive controller
# cannot probe upward against a municipal server), max_concurrent=1.
#
# None of that is self-enforcing. `run_service` binds the limiter and robots
# context around `start_run`, but they are only read inside `limited_get` — so a
# provider calling `client.get` directly silently bypasses the entire policy.
# Every other implemented provider routes through `limited_get`; this one did
# not, which meant the policy was declared and inert. Going LIVE is what would
# have made that reachable behind a single admin toggle.


class _DenyAllRobots(RobotsChecker):
    async def is_allowed(self, url: str, user_agent: str) -> bool:  # noqa: ARG002
        return False


@pytest.mark.asyncio
async def test_provider_honours_a_strict_robots_context(monkeypatch: pytest.MonkeyPatch) -> None:
    """A strict robots deny must stop the fetch, not merely be recorded.

    Asserted at the provider boundary rather than on `limited_get` itself: the
    defect this guards is a provider that never calls it.
    """
    captured = _install_fake_client(
        monkeypatch,
        {
            "https://www.stadt-zuerich.ch/de/": (
                200,
                _fixture_html(),
                {"content-type": "text/html; charset=utf-8"},
            ),
        },
    )
    provider = GemeindeHttpProvider()
    source_version = SimpleNamespace(
        acquisition_spec={"bfs_number": 261, "seed_url": LANDING_URL},
    )

    token = current_robots_context.set(
        RobotsContext(checker=_DenyAllRobots(), mode=RobotsMode.STRICT, user_agent="evidara-bot")
    )
    try:
        result = await provider.start_run(
            SimpleNamespace(),
            source_version,
            SimpleNamespace(run_id="run_robots_denied"),
        )
    finally:
        current_robots_context.reset(token)

    # The request must not have been made at all.
    assert captured.calls == []
    assert result.response_payload["captured"] == 0


@pytest.mark.asyncio
async def test_provider_consumes_the_run_rate_limiter(monkeypatch: pytest.MonkeyPatch) -> None:
    # The flat 10 rpm ceiling only binds if the provider actually acquires tokens.
    acquired: list[str] = []

    class _Permit:
        async def __aenter__(self) -> _Permit:
            return self

        async def __aexit__(self, *exc: object) -> None:
            del exc

    class _SpyLimiter:
        # `acquire` takes a host and returns an async context-manager permit;
        # returning None here would blow up inside the provider's own try/except
        # and be swallowed as an acquisition failure.
        async def acquire(self, host: str) -> _Permit:
            acquired.append(host)
            return _Permit()

        def observe(self, *args: object, **kwargs: object) -> None:
            del args, kwargs

    _install_fake_client(
        monkeypatch,
        {
            "https://www.stadt-zuerich.ch/de/": (
                200,
                _fixture_html(),
                {"content-type": "text/html; charset=utf-8"},
            ),
            "https://www.stadt-zuerich.ch/dam/": (
                200,
                _PDF_BYTES,
                {"content-type": "application/pdf"},
            ),
        },
    )
    provider = GemeindeHttpProvider()
    token = current_rate_limiter.set(_SpyLimiter())
    try:
        await provider.start_run(
            SimpleNamespace(),
            SimpleNamespace(acquisition_spec={"bfs_number": 261, "seed_url": LANDING_URL}),
            SimpleNamespace(run_id="run_rate_limited"),
        )
    finally:
        current_rate_limiter.reset(token)

    # Landing page + the linked PDF: both go through the limiter, both on the
    # commune's host — which is what the flat per-host ceiling binds.
    assert acquired == ["www.stadt-zuerich.ch", "www.stadt-zuerich.ch"]


@pytest.mark.asyncio
async def test_an_unparseable_portal_says_so_rather_than_just_captured_nothing(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    """#784: the run already failed; it just would not say why.

    A commune on a differently-shaped portal reaches a real page with no
    Amtliche-Sammlung fields on it. The run correctly fails, but the operator-facing
    reason used to be `did not capture any resources for BFS 261` — which reads
    identically to wrong seeds or a portal outage, and points at neither remedy.

    The distinguishing fact was already collected in `failures`; it was thrown away
    on the way to `failure_reason`.
    """
    _install_fake_client(
        monkeypatch,
        {
            "https://www.stadt-zuerich.ch/de/": (
                200,
                "<html><head><title>Willkommen</title></head><body><p>Kein AS</p></body></html>",
                {"content-type": "text/html; charset=utf-8"},
            ),
        },
    )
    provider = GemeindeHttpProvider()
    source_version = SimpleNamespace(acquisition_spec={"bfs_number": 261, "seed_url": LANDING_URL})
    result = await provider.start_run(
        SimpleNamespace(),
        source_version,
        SimpleNamespace(run_id="run_zh_261_unparseable"),
    )

    assert result.response_payload["captured"] == 0
    # It still fails — this was already true and is the half #784 got wrong.
    assert result.inline_failure_reason is not None

    reason = result.inline_failure_reason
    # …and now names the actual condition and the actual remedy.
    assert "no operative-text link" in reason
    assert "needs a parser" in reason
    # The old generic sentence must not be what an operator reads here.
    assert reason != "gemeinde_http did not capture any resources for BFS 261"


@pytest.mark.asyncio
async def test_a_transport_failure_is_not_reported_as_an_unparseable_portal(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    """The two causes must stay distinguishable, or the new message is just a new lie.

    An unreachable page and an unrecognised page shape need different remedies —
    retry/fix the seed versus write a parser. A message that claimed "needs a
    parser" for a 500 would be worse than the generic one it replaced.
    """
    _install_fake_client(
        monkeypatch,
        {
            "https://www.stadt-zuerich.ch/de/": (
                500,
                "upstream exploded",
                {"content-type": "text/html; charset=utf-8"},
            ),
        },
    )
    provider = GemeindeHttpProvider()
    source_version = SimpleNamespace(acquisition_spec={"bfs_number": 261, "seed_url": LANDING_URL})
    result = await provider.start_run(
        SimpleNamespace(),
        source_version,
        SimpleNamespace(run_id="run_zh_261_transport"),
    )

    assert result.response_payload["captured"] == 0
    reason = result.inline_failure_reason
    assert reason is not None
    assert "needs a parser" not in reason
    # The per-URL cause is surfaced instead of being left in the payload.
    assert "https://www.stadt-zuerich.ch/de/" in reason
