"""Unit tests for the CH canton HTTP provider.

WHY THESE TESTS EXIST:
- Config-driven multi-tenant: `canton_http` shares `PortalHttpProviderBase`
  with the DE/IT subdivision-portal providers. A bug in the CH subclass
  config (portal allow-list, subdivision country) would silently leak
  across every canton tenant.
- Host allow-list: the base enforces that seed URLs match the portal host
  registered for the ISO 3166-2:CH code. Critical for safety — prevents
  operators from pointing a CH-ZH template at a random host.
- Subdivision-code validation: only ISO 3166-2:CH codes with a supported
  portal are accepted.
"""

from __future__ import annotations

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
from platform_control.services.canton_http_provider import CantonHttpProvider


class _FakePortalClient:
    """Captures requested URLs and returns canned HTML per URL prefix."""

    def __init__(self, responses: dict[str, tuple[int, str, dict[str, str]]]) -> None:
        self.responses = responses
        self.calls: list[str] = []

    async def __aenter__(self) -> _FakePortalClient:
        return self

    async def __aexit__(self, exc_type, exc, tb) -> None:
        del exc_type, exc, tb

    async def get(self, url: str):
        self.calls.append(url)
        for prefix, (status, body, headers) in self.responses.items():
            if url.startswith(prefix):
                request = httpx.Request("GET", url)
                return httpx.Response(status, text=body, headers=headers, request=request)
        raise AssertionError(f"unexpected URL: {url}")


def _install_fake_client(
    monkeypatch: pytest.MonkeyPatch,
    responses: dict[str, tuple[int, str, dict[str, str]]],
) -> _FakePortalClient:
    captured = _FakePortalClient(responses)

    def factory(*args, **kwargs):
        del args, kwargs
        return captured

    monkeypatch.setattr(httpx, "AsyncClient", factory)
    return captured


# ─── Zürich (CH-ZH) ─────────────────────────────────────────────


@pytest.mark.asyncio
async def test_zurich_end_to_end_fetches_seed_and_emits_resource(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    _install_fake_client(
        monkeypatch,
        {
            "https://www.zh.ch/": (
                200,
                "<html><head>"
                "<title>\n  LS 131.1 – Verfassung des\n  Kantons Zürich</title>"
                "</head><body><h1>Art. 1</h1>"
                "<p>Art. 2 Abs. 1: Der Kanton ...</p>"
                "<p>Art. 3 Abs. 2 ...</p></body></html>",
                {"content-type": "text/html; charset=utf-8"},
            )
        },
    )
    provider = CantonHttpProvider()
    source_version = SimpleNamespace(
        acquisition_spec={
            "canton_code": "CH-ZH",
            "seed_url": "https://www.zh.ch/de/politik-staat/gesetze.html",
        }
    )
    result = await provider.start_run(
        SimpleNamespace(),
        source_version,
        SimpleNamespace(run_id="run_ch_zh_1"),
    )
    assert result.response_payload["captured"] == 1
    assert result.response_payload["failed"] == 0
    assert result.response_payload["canton_code"] == "CH-ZH"
    payload = result.inline_resources[0]
    # Title whitespace collapsed by _extract_title.
    assert payload.title == "LS 131.1 – Verfassung des Kantons Zürich"
    assert payload.content_type == "text/html"
    assert payload.metadata["canton_code"] == "CH-ZH"
    assert payload.metadata["subdivision"] == "CH-ZH"
    assert payload.metadata["portal_host"] == "www.zh.ch"


@pytest.mark.asyncio
async def test_canton_provider_accepts_subdomain_seed(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    _install_fake_client(
        monkeypatch,
        {
            "https://www.belex.sites.be.ch/": (
                200,
                "<html><head><title>BELEX</title></head><body>"
                "<p>Art. 1</p><p>Art. 2 Abs. 1</p><p>Art. 3</p></body></html>",
                {"content-type": "text/html"},
            )
        },
    )
    provider = CantonHttpProvider()
    source_version = SimpleNamespace(
        acquisition_spec={
            "canton_code": "CH-BE",
            "seed_url": "https://www.belex.sites.be.ch/frontend/texts_of_law",
        }
    )
    result = await provider.start_run(
        SimpleNamespace(),
        source_version,
        SimpleNamespace(run_id="run_ch_be_1"),
    )
    assert result.response_payload["captured"] == 1


@pytest.mark.asyncio
async def test_canton_provider_rejects_seed_from_foreign_host(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    _install_fake_client(monkeypatch, {})
    provider = CantonHttpProvider()
    source_version = SimpleNamespace(
        acquisition_spec={
            "canton_code": "CH-ZH",
            "seed_url": "https://attacker.example.com/exfil",
        }
    )
    with pytest.raises(ProviderConfigurationError, match="host must match"):
        await provider.start_run(
            SimpleNamespace(),
            source_version,
            SimpleNamespace(run_id="run_x"),
        )


@pytest.mark.asyncio
async def test_canton_provider_rejects_unknown_code() -> None:
    provider = CantonHttpProvider()
    source_version = SimpleNamespace(
        acquisition_spec={
            "canton_code": "CH-XX",
            "seed_url": "https://whatever.example/",
        }
    )
    with pytest.raises(ProviderConfigurationError, match="no supported portal"):
        await provider.start_run(
            SimpleNamespace(),
            source_version,
            SimpleNamespace(run_id="run_x"),
        )


@pytest.mark.asyncio
async def test_canton_provider_rejects_non_ch_code() -> None:
    provider = CantonHttpProvider()
    source_version = SimpleNamespace(
        acquisition_spec={"canton_code": "DE-BY", "seed_url": "https://x/"}
    )
    with pytest.raises(ProviderConfigurationError, match="ISO 3166-2:CH"):
        await provider.start_run(
            SimpleNamespace(),
            source_version,
            SimpleNamespace(run_id="run_x"),
        )


@pytest.mark.asyncio
async def test_canton_provider_requires_subdivision_key() -> None:
    provider = CantonHttpProvider()
    source_version = SimpleNamespace(acquisition_spec={"seed_url": "https://www.zh.ch/"})
    with pytest.raises(ProviderConfigurationError, match="requires"):
        await provider.start_run(
            SimpleNamespace(),
            source_version,
            SimpleNamespace(run_id="run_x"),
        )


@pytest.mark.asyncio
async def test_canton_provider_requires_seed_urls() -> None:
    provider = CantonHttpProvider()
    source_version = SimpleNamespace(acquisition_spec={"canton_code": "CH-ZH"})
    with pytest.raises(ProviderConfigurationError, match="seed_url"):
        await provider.start_run(
            SimpleNamespace(),
            source_version,
            SimpleNamespace(run_id="run_x"),
        )


# ─── Legal-text density gate (#631) ─────────────────────────────


@pytest.mark.asyncio
async def test_canton_provider_refuses_javascript_navigation_shell(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    """A JS SPA nav shell (no legal-text markers) must be refused, not captured.

    Regression for #631: canton_http fetched the live zh.ch portal, captured a
    177 KB navigation shell that is ~95% script/style with zero Art./§/Abs.
    markers, and reported a clean success (captured=1, failed=0). It must refuse
    honestly — like gemeinde_http does — rather than poison the corpus.
    """
    nav_shell = (
        "<html><head><title>Kanton Zürich</title>"
        "<style>.nav{color:red}</style>"
        "<script>window.__APP__={routes:['/home','/politik-staat']};</script>"
        "</head><body>"
        "<nav>Startseite Politik &amp; Staat Verwaltung Kontakt Suche Login</nav>"
        "<script>document.getElementById('app').render();</script>"
        "<script>function track(){/* analytics chrome, no law here */}</script>"
        "</body></html>"
    )
    _install_fake_client(
        monkeypatch,
        {
            "https://www.zh.ch/": (
                200,
                nav_shell,
                {"content-type": "text/html; charset=utf-8"},
            )
        },
    )
    provider = CantonHttpProvider()
    source_version = SimpleNamespace(
        acquisition_spec={
            "canton_code": "CH-ZH",
            "seed_url": "https://www.zh.ch/de/politik-staat/gesetze.html",
        }
    )
    result = await provider.start_run(
        SimpleNamespace(),
        source_version,
        SimpleNamespace(run_id="run_ch_zh_shell"),
    )
    # Honest refusal: nothing captured, the shell recorded as skipped with a
    # reason — never a clean success on chrome.
    assert result.response_payload["captured"] == 0
    assert result.response_payload["skipped"] == 1
    assert result.inline_resources == []
    assert result.inline_failure_reason is not None
    assert "density gate" in result.inline_failure_reason
    skipped = result.response_payload["skipped_documents"][0]
    assert skipped["reason"] == "no_legal_text_markers"
    assert skipped["legal_marker_count"] == 0


def test_canton_http_provider_is_a_scaffold() -> None:
    # A genuine scaffold, unlike gemeinde_http/ch_court_decisions: start_run is
    # not implemented, so there is nothing for an acceptance run to gather
    # evidence about. Even mode=acceptance must refuse (#743).
    assert provider_readiness(CantonHttpProvider) is AcquisitionReadiness.SCAFFOLD
    with pytest.raises(ProviderNotLiveReadyError) as excinfo:
        ensure_launchable(CantonHttpProvider, for_acceptance=True)
    assert "scaffold" in str(excinfo.value)
