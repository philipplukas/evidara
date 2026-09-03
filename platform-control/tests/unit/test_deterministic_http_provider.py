from __future__ import annotations

from types import SimpleNamespace

import httpx
import pytest

from platform_control.errors import ProviderConfigurationError
from platform_control.services.deterministic_http_provider import DeterministicHttpProvider
from platform_control.services.politeness import HostRateLimiter


def _source_version_with_spec(spec: dict) -> SimpleNamespace:
    return SimpleNamespace(acquisition_spec=spec)


def _run(run_id: str = "run_test_123") -> SimpleNamespace:
    return SimpleNamespace(run_id=run_id)


@pytest.mark.asyncio
async def test_start_run_blocks_restricted_hostname_without_network() -> None:
    provider = DeterministicHttpProvider()
    result = await provider.start_run(
        source=SimpleNamespace(),
        source_version=_source_version_with_spec(
            {
                "provider": "deterministic_http",
                "seed_url": "http://metadata.google.internal",
            }
        ),
        run=_run(),
    )

    assert result.response_payload["captured"] == 0
    assert result.response_payload["failed"] == 1
    assert "blocked restricted host" in result.response_payload["failures"][0]["error"]
    assert result.inline_failure_reason is not None


@pytest.mark.asyncio
async def test_start_run_skips_non_success_responses(monkeypatch: pytest.MonkeyPatch) -> None:
    provider = DeterministicHttpProvider()

    async def fake_request_with_safe_redirects(*, client, url, headers):
        del client, headers
        response = httpx.Response(
            403,
            request=httpx.Request("GET", url),
            headers={"content-type": "text/plain"},
        )
        return url, response

    monkeypatch.setattr(provider, "_request_with_safe_redirects", fake_request_with_safe_redirects)

    result = await provider.start_run(
        source=SimpleNamespace(),
        source_version=_source_version_with_spec(
            {"provider": "deterministic_http", "seed_url": "https://example.com"}
        ),
        run=_run(),
    )

    assert result.response_payload["captured"] == 0
    assert result.response_payload["failed"] == 1
    assert "received non-success status 403" in result.response_payload["failures"][0]["error"]


@pytest.mark.asyncio
async def test_start_run_enforces_max_content_bytes(monkeypatch: pytest.MonkeyPatch) -> None:
    provider = DeterministicHttpProvider()

    async def fake_request_with_safe_redirects(*, client, url, headers):
        del client, headers
        response = httpx.Response(
            200,
            request=httpx.Request("GET", url),
            content=b"ok",
            headers={"content-type": "text/plain"},
        )
        return url, response

    async def fake_read_body_limited(*, response, max_content_bytes):
        del response, max_content_bytes
        return None

    monkeypatch.setattr(provider, "_request_with_safe_redirects", fake_request_with_safe_redirects)
    monkeypatch.setattr(provider, "_read_body_limited", fake_read_body_limited)

    result = await provider.start_run(
        source=SimpleNamespace(),
        source_version=_source_version_with_spec(
            {
                "provider": "deterministic_http",
                "seed_url": "https://example.com",
                "max_content_bytes": 1,
            }
        ),
        run=_run(),
    )

    assert result.response_payload["captured"] == 0
    assert result.response_payload["failed"] == 1
    assert (
        "response exceeded max_content_bytes=1" in (result.response_payload["failures"][0]["error"])
    )


def test_validate_target_url_blocks_private_ip_resolution(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    provider = DeterministicHttpProvider()

    def fake_getaddrinfo(host, port):
        del host, port
        return [(0, 0, 0, "", ("10.0.0.1", 0))]

    monkeypatch.setattr("socket.getaddrinfo", fake_getaddrinfo)

    with pytest.raises(ProviderConfigurationError, match="blocked restricted address"):
        provider._validate_target_url("https://example.com/path")


def test_validate_target_url_allows_public_resolution(monkeypatch: pytest.MonkeyPatch) -> None:
    provider = DeterministicHttpProvider()

    def fake_getaddrinfo(host, port):
        del host, port
        return [(0, 0, 0, "", ("93.184.216.34", 0))]

    monkeypatch.setattr("socket.getaddrinfo", fake_getaddrinfo)

    assert provider._validate_target_url("https://example.com/path") == "https://example.com/path"


class _SpyLimiter(HostRateLimiter):
    def __init__(self) -> None:
        super().__init__(max_requests_per_minute=60, max_concurrent=2)
        self.acquired_hosts: list[str] = []

    async def acquire(self, host: str):
        self.acquired_hosts.append(host)
        return await super().acquire(host)


class _StubAsyncClient:
    def __init__(self) -> None:
        self.calls: list[str] = []

    async def get(self, url: str, headers: dict[str, str]) -> httpx.Response:
        del headers
        self.calls.append(url)
        return httpx.Response(
            200,
            request=httpx.Request("GET", url),
            content=b"ok",
            headers={"content-type": "text/plain"},
        )


@pytest.mark.asyncio
async def test_get_with_rate_limit_consults_limiter_per_host() -> None:
    limiter = _SpyLimiter()
    provider = DeterministicHttpProvider(rate_limiter=limiter)
    client = _StubAsyncClient()

    response = await provider._get_with_rate_limit(
        client=client, url="https://example.com/a", headers={}
    )

    assert response.status_code == 200
    assert client.calls == ["https://example.com/a"]
    assert limiter.acquired_hosts == ["example.com"]


@pytest.mark.asyncio
async def test_get_with_rate_limit_noop_when_no_limiter() -> None:
    provider = DeterministicHttpProvider()
    client = _StubAsyncClient()

    response = await provider._get_with_rate_limit(
        client=client, url="https://example.com/b", headers={}
    )

    assert response.status_code == 200
    assert client.calls == ["https://example.com/b"]


# ─── The legal-text density gate (#631) ─────────────────────────
#
# Every blueprint template pointing at this provider targets a DE/CH/IT collection
# (source_blueprints.yaml:114,129,176,672), which is the vocabulary `content_gate`
# was built for. Mutation check: delete the `assess_legal_text_density(...)` block in
# `start_run` and `test_navigation_shell_is_refused...` fails with `captured == 1`.


def _serving(body: bytes, content_type: str):
    async def fake_request_with_safe_redirects(*, client, url, headers):
        del client, headers
        return url, httpx.Response(
            200,
            request=httpx.Request("GET", url),
            content=body,
            headers={"content-type": content_type},
        )

    return fake_request_with_safe_redirects


@pytest.mark.asyncio
async def test_navigation_shell_is_refused_rather_than_captured_as_law(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    provider = DeterministicHttpProvider()
    monkeypatch.setattr(
        provider,
        "_request_with_safe_redirects",
        _serving(
            b"<html><head><script>var app=1;</script></head><body>"
            b"<nav>Startseite Impressum Datenschutz</nav></body></html>",
            "text/html; charset=utf-8",
        ),
    )

    result = await provider.start_run(
        source=SimpleNamespace(),
        source_version=_source_version_with_spec(
            {"provider": "deterministic_http", "seed_url": "https://www.gesetze-im-internet.de/x"}
        ),
        run=_run("run_shell"),
    )

    assert result.response_payload["captured"] == 0
    assert result.inline_resources == []
    assert result.response_payload["skipped"] == 1
    assert result.response_payload["skipped_documents"][0]["reason"] == "no_legal_text_markers"
    assert "legal-text density gate" in result.inline_failure_reason


@pytest.mark.asyncio
async def test_a_genuine_statute_page_passes_and_carries_its_verdict(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    provider = DeterministicHttpProvider()
    monkeypatch.setattr(
        provider,
        "_request_with_safe_redirects",
        _serving(
            "<html><body><h1>Bundes-Immissionsschutzgesetz</h1>"
            "<p>§ 1 Zweck des Gesetzes ...</p>"
            "<p>§ 2 Abs. 1 Geltungsbereich ...</p>"
            "<p>§ 3 Abs. 2 Ziff. 1 Begriffsbestimmungen ...</p>"
            "</body></html>".encode(),
            "text/html; charset=utf-8",
        ),
    )

    result = await provider.start_run(
        source=SimpleNamespace(),
        source_version=_source_version_with_spec(
            {"provider": "deterministic_http", "seed_url": "https://www.gesetze-im-internet.de/y"}
        ),
        run=_run("run_ok"),
    )

    assert result.response_payload["captured"] == 1
    metadata = result.inline_resources[0].metadata
    assert metadata["legal_text_assessment"] == "passed"
    assert metadata["legal_text_evidence"]["legal_marker_count"] >= 3


@pytest.mark.asyncio
async def test_the_gate_abstains_on_a_content_type_it_cannot_read(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    """A marker floor on `text/plain` would refuse honest captures, so it abstains.

    This is the failure mode the wiring has to avoid: a gate configured for the
    wrong modality is worse than no gate, because it rejects real documents.
    """
    provider = DeterministicHttpProvider()
    monkeypatch.setattr(
        provider,
        "_request_with_safe_redirects",
        _serving(b"Ein Gesetzestext ohne Markierungen.", "text/plain; charset=utf-8"),
    )

    result = await provider.start_run(
        source=SimpleNamespace(),
        source_version=_source_version_with_spec(
            {"provider": "deterministic_http", "seed_url": "https://www.gesetze-im-internet.de/z"}
        ),
        run=_run("run_plain"),
    )

    assert result.response_payload["captured"] == 1
    assert result.response_payload["skipped"] == 0
