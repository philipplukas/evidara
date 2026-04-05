from __future__ import annotations

from types import SimpleNamespace

import httpx
import pytest

from platform_control.errors import ProviderConfigurationError
from platform_control.services.deterministic_http_provider import DeterministicHttpProvider


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
    assert "response exceeded max_content_bytes=1" in (
        result.response_payload["failures"][0]["error"]
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
