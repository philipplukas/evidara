"""Unit tests for DE Bundesland and IT regione HTTP providers.

WHY THESE TESTS EXIST:
- Config-driven multi-tenant: `bundesland_http` and `regione_http`
  share `PortalHttpProviderBase`. A bug in the base or in a subclass
  config would silently leak across every tenant.
- Host allow-list: the base enforces that seed URLs match the portal
  host registered for the ISO 3166-2 code. Critical for safety —
  prevents operators from pointing a DE-BY template at a random host.
- Title extraction: the provider emits `ProviderResource.title` via
  `<title>` parsing. Must handle multi-line titles and whitespace.
"""

from __future__ import annotations

from types import SimpleNamespace

import httpx
import pytest

from platform_control.errors import ProviderConfigurationError
from platform_control.services.bundesland_http_provider import (
    BundeslandHttpProvider,
)
from platform_control.services.regione_http_provider import (
    RegioneHttpProvider,
)


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
                return httpx.Response(
                    status,
                    text=body,
                    headers=headers,
                    request=request,
                )
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


# ─── Bayern (DE-BY) ─────────────────────────────────────────────


@pytest.mark.asyncio
async def test_bayern_end_to_end_fetches_seed_and_emits_resource(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    _install_fake_client(
        monkeypatch,
        {
            "https://www.gesetze-bayern.de/": (
                200,
                "<html><head>"
                "<title>\n  BayVwVfG – Bayerisches\n  Verwaltungsverfahrensgesetz</title>"
                "</head><body><h1>Art. 1 Geltungsbereich</h1>"
                "<p>Art. 2 Abs. 1: Dieses Gesetz gilt ...</p>"
                "<p>Art. 3 Abs. 2 Ziff. 1 ...</p></body></html>",
                {"content-type": "text/html; charset=utf-8"},
            )
        },
    )
    provider = BundeslandHttpProvider()
    source_version = SimpleNamespace(
        acquisition_spec={
            "bundesland": "DE-BY",
            "seed_url": "https://www.gesetze-bayern.de/",
        }
    )
    result = await provider.start_run(
        SimpleNamespace(),
        source_version,
        SimpleNamespace(run_id="run_de_by_1"),
    )
    assert result.response_payload["captured"] == 1
    assert result.response_payload["failed"] == 0
    assert result.response_payload["bundesland"] == "DE-BY"
    payload = result.inline_resources[0]
    # Title whitespace collapsed by _extract_title.
    assert payload.title == "BayVwVfG – Bayerisches Verwaltungsverfahrensgesetz"
    assert payload.content_type == "text/html"
    assert payload.metadata["bundesland"] == "DE-BY"
    assert payload.metadata["subdivision"] == "DE-BY"
    assert payload.metadata["portal_host"] == "www.gesetze-bayern.de"


@pytest.mark.asyncio
async def test_bundesland_provider_accepts_subdomain_seed(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    _install_fake_client(
        monkeypatch,
        {
            "https://sub.recht.nrw.de/": (
                200,
                "<html><head><title>NRW-Landesrecht</title></head><body>"
                "<p>Art. 1</p><p>Art. 2 Abs. 1</p><p>§ 3</p></body></html>",
                {"content-type": "text/html"},
            )
        },
    )
    provider = BundeslandHttpProvider()
    source_version = SimpleNamespace(
        acquisition_spec={
            "bundesland": "DE-NW",
            "seed_url": "https://sub.recht.nrw.de/statute/1",
        }
    )
    result = await provider.start_run(
        SimpleNamespace(),
        source_version,
        SimpleNamespace(run_id="run_de_nw_1"),
    )
    assert result.response_payload["captured"] == 1


@pytest.mark.asyncio
async def test_bundesland_provider_rejects_seed_from_foreign_host(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    _install_fake_client(monkeypatch, {})
    provider = BundeslandHttpProvider()
    source_version = SimpleNamespace(
        acquisition_spec={
            "bundesland": "DE-BY",
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
async def test_bundesland_provider_rejects_unknown_code() -> None:
    provider = BundeslandHttpProvider()
    source_version = SimpleNamespace(
        acquisition_spec={
            "bundesland": "DE-XX",
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
async def test_bundesland_provider_rejects_non_de_code() -> None:
    provider = BundeslandHttpProvider()
    source_version = SimpleNamespace(
        acquisition_spec={"bundesland": "AT-9", "seed_url": "https://x/"}
    )
    with pytest.raises(ProviderConfigurationError, match="ISO 3166-2:DE"):
        await provider.start_run(
            SimpleNamespace(),
            source_version,
            SimpleNamespace(run_id="run_x"),
        )


@pytest.mark.asyncio
async def test_bundesland_provider_requires_subdivision_key() -> None:
    provider = BundeslandHttpProvider()
    source_version = SimpleNamespace(
        acquisition_spec={"seed_url": "https://www.gesetze-bayern.de/"}
    )
    with pytest.raises(ProviderConfigurationError, match="requires"):
        await provider.start_run(
            SimpleNamespace(),
            source_version,
            SimpleNamespace(run_id="run_x"),
        )


@pytest.mark.asyncio
async def test_bundesland_provider_requires_seed_urls() -> None:
    provider = BundeslandHttpProvider()
    source_version = SimpleNamespace(acquisition_spec={"bundesland": "DE-BY"})
    with pytest.raises(ProviderConfigurationError, match="seed_url"):
        await provider.start_run(
            SimpleNamespace(),
            source_version,
            SimpleNamespace(run_id="run_x"),
        )


# ─── Lombardia (IT-25) ──────────────────────────────────────────


@pytest.mark.asyncio
async def test_lombardia_end_to_end_fetches_seed_and_emits_resource(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    _install_fake_client(
        monkeypatch,
        {
            "https://normelombardia.consiglio.regione.lombardia.it/": (
                200,
                "<html><head>"
                "<title>L.R. 12/2005 – Legge per il governo del territorio</title>"
                "</head><body><p>art. 1 comma 1</p><p>art. 2 comma 2</p>"
                "<p>art. 3</p></body></html>",
                {"content-type": "text/html; charset=utf-8"},
            )
        },
    )
    provider = RegioneHttpProvider()
    source_version = SimpleNamespace(
        acquisition_spec={
            "regione": "IT-25",
            "seed_url": "https://normelombardia.consiglio.regione.lombardia.it/",
        }
    )
    result = await provider.start_run(
        SimpleNamespace(),
        source_version,
        SimpleNamespace(run_id="run_it_25_1"),
    )
    assert result.response_payload["captured"] == 1
    assert result.response_payload["regione"] == "IT-25"
    payload = result.inline_resources[0]
    assert payload.title.startswith("L.R. 12/2005")
    assert payload.metadata["regione"] == "IT-25"
    assert payload.metadata["subdivision"] == "IT-25"
    assert payload.metadata["portal_host"] == "normelombardia.consiglio.regione.lombardia.it"


@pytest.mark.asyncio
async def test_regione_provider_rejects_non_it_code() -> None:
    provider = RegioneHttpProvider()
    source_version = SimpleNamespace(
        acquisition_spec={"regione": "DE-BY", "seed_url": "https://x/"}
    )
    with pytest.raises(ProviderConfigurationError, match="ISO 3166-2:IT"):
        await provider.start_run(
            SimpleNamespace(),
            source_version,
            SimpleNamespace(run_id="run_x"),
        )


# ─── Base helpers ───────────────────────────────────────────────


def test_extract_title_returns_none_for_missing_title_tag() -> None:
    assert BundeslandHttpProvider._extract_title("<html><body>no head</body></html>") is None


def test_extract_title_collapses_whitespace() -> None:
    body = "<html><head><title>\n  Gesetz\n\t über  X</title></head></html>"
    assert BundeslandHttpProvider._extract_title(body) == "Gesetz über X"


def test_extract_title_handles_attributes_on_title_tag() -> None:
    body = '<html><head><title lang="de">Statute</title></head></html>'
    assert BundeslandHttpProvider._extract_title(body) == "Statute"


def _page(title: str) -> tuple[int, str, dict[str, str]]:
    return (
        200,
        f"<html><head><title>{title}</title></head><body>"
        "<h1>Art. 1 Geltungsbereich</h1>"
        "<p>Art. 2 Abs. 1: Dieses Gesetz gilt ...</p>"
        "<p>Art. 3 Abs. 2 Ziff. 1 ...</p></body></html>",
        {"content-type": "text/html; charset=utf-8"},
    )


async def test_run_scope_max_resources_caps_the_seed_list(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    """`scope.max_resources` narrows a run without a source-version change (#1010).

    It was accepted by the API, stored on the run and read by nothing: a
    `max_resources: 25` acceptance run on `lexfind_api_zh_full` published 944
    documents on 2026-09-17. Portal providers declare no ceiling of their own, so
    the run scope is the only cap there is.
    """
    seeds = [
        "https://www.gesetze-bayern.de/a",
        "https://www.gesetze-bayern.de/b",
        "https://www.gesetze-bayern.de/c",
    ]
    _install_fake_client(monkeypatch, {url: _page(f"Gesetz {url[-1].upper()}") for url in seeds})

    result = await BundeslandHttpProvider().start_run(
        SimpleNamespace(),
        SimpleNamespace(acquisition_spec={"bundesland": "DE-BY", "seed_urls": seeds}),
        SimpleNamespace(run_id="run_capped", run_metadata={"scope": {"max_resources": 2}}),
    )

    assert result.response_payload["captured"] == 2
    assert len(result.inline_resources) == 2
    # The first two, in order — a cap samples the head of the declared list rather
    # than an arbitrary subset, so a capped run is reproducible.
    assert [r.source_url for r in result.inline_resources] == seeds[:2]


async def test_without_a_run_scope_every_seed_is_fetched(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    """The cap must be opt-in: an uncapped run behaves exactly as before.

    Without this, the test above would pass just as well if the provider had
    started dropping seeds for some unrelated reason.
    """
    seeds = [
        "https://www.gesetze-bayern.de/a",
        "https://www.gesetze-bayern.de/b",
        "https://www.gesetze-bayern.de/c",
    ]
    _install_fake_client(monkeypatch, {url: _page(f"Gesetz {url[-1].upper()}") for url in seeds})

    result = await BundeslandHttpProvider().start_run(
        SimpleNamespace(),
        SimpleNamespace(acquisition_spec={"bundesland": "DE-BY", "seed_urls": seeds}),
        SimpleNamespace(run_id="run_uncapped"),
    )

    assert result.response_payload["captured"] == 3
