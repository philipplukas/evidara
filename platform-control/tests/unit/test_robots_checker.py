from __future__ import annotations

import httpx
import pytest

from platform_control.services.robots import RobotsChecker


def _transport_for(response_map: dict[str, tuple[int, str]]) -> httpx.MockTransport:
    def handler(request: httpx.Request) -> httpx.Response:
        status, body = response_map.get(str(request.url), (404, ""))
        return httpx.Response(status, text=body)

    return httpx.MockTransport(handler)


class _ClockedChecker(RobotsChecker):
    """Variant that injects both the HTTP transport and the monotonic clock."""

    def __init__(self, transport: httpx.MockTransport, *, ttl_seconds: int = 3600):
        super().__init__(ttl_seconds=ttl_seconds)
        self._transport = transport

    async def _fetch_and_parse(self, origin: str):  # type: ignore[override]
        from urllib.robotparser import RobotFileParser

        async with httpx.AsyncClient(transport=self._transport) as client:
            response = await client.get(f"{origin}/robots.txt")
        if response.status_code >= 500:
            return None
        if response.status_code >= 400:
            return None
        parser = RobotFileParser()
        parser.parse(response.text.splitlines())
        return parser


@pytest.mark.asyncio
async def test_allows_when_no_robots_file() -> None:
    transport = _transport_for({})  # default 404 for robots.txt
    checker = _ClockedChecker(transport)

    allowed = await checker.is_allowed("https://example.com/page", "evidara-bot")

    assert allowed is True


@pytest.mark.asyncio
async def test_respects_disallow_rule_for_user_agent() -> None:
    robots_body = "User-agent: *\nDisallow: /private/\n"
    transport = _transport_for({"https://example.com/robots.txt": (200, robots_body)})
    checker = _ClockedChecker(transport)

    assert (
        await checker.is_allowed("https://example.com/private/secret", "evidara-bot")
        is False
    )
    assert (
        await checker.is_allowed("https://example.com/public/page", "evidara-bot")
        is True
    )


@pytest.mark.asyncio
async def test_allows_on_server_error() -> None:
    transport = _transport_for({"https://example.com/robots.txt": (503, "unavailable")})
    checker = _ClockedChecker(transport)

    allowed = await checker.is_allowed("https://example.com/anything", "evidara-bot")

    assert allowed is True


@pytest.mark.asyncio
async def test_caches_per_origin(monkeypatch: pytest.MonkeyPatch) -> None:
    call_count = 0

    def handler(request: httpx.Request) -> httpx.Response:
        nonlocal call_count
        call_count += 1
        return httpx.Response(200, text="User-agent: *\nAllow: /\n")

    transport = httpx.MockTransport(handler)
    checker = _ClockedChecker(transport)

    await checker.is_allowed("https://a.example/x", "evidara-bot")
    await checker.is_allowed("https://a.example/y", "evidara-bot")
    await checker.is_allowed("https://a.example/z", "evidara-bot")

    assert call_count == 1


@pytest.mark.asyncio
async def test_url_without_host_is_allowed() -> None:
    checker = RobotsChecker()

    # Relative URL => no host => the checker cannot apply robots and must allow.
    assert await checker.is_allowed("/nohost", "evidara-bot") is True
