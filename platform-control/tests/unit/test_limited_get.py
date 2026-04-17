from __future__ import annotations

import httpx
import pytest

from platform_control.domain import RobotsMode
from platform_control.services.politeness import (
    HostRateLimiter,
    current_rate_limiter,
    limited_get,
)
from platform_control.services.robots import (
    RobotsChecker,
    RobotsContext,
    RobotsDisallowedError,
    current_robots_context,
)


class _StubClient:
    def __init__(self) -> None:
        self.calls: list[str] = []

    async def get(self, url: str, **kwargs) -> httpx.Response:
        del kwargs
        self.calls.append(url)
        return httpx.Response(
            200,
            request=httpx.Request("GET", url),
            content=b"ok",
            headers={"content-type": "text/plain"},
        )


class _SpyLimiter(HostRateLimiter):
    def __init__(self) -> None:
        super().__init__(max_requests_per_minute=60, max_concurrent=2)
        self.acquired: list[str] = []

    async def acquire(self, host: str):
        self.acquired.append(host)
        return await super().acquire(host)


@pytest.mark.asyncio
async def test_limited_get_bypasses_when_no_limiter_set() -> None:
    client = _StubClient()

    response = await limited_get(client, "https://example.com/a")

    assert response.status_code == 200
    assert client.calls == ["https://example.com/a"]


@pytest.mark.asyncio
async def test_limited_get_uses_explicit_limiter_over_contextvar() -> None:
    explicit = _SpyLimiter()
    fallback = _SpyLimiter()
    client = _StubClient()

    token = current_rate_limiter.set(fallback)
    try:
        await limited_get(client, "https://example.com/a", limiter=explicit)
    finally:
        current_rate_limiter.reset(token)

    assert explicit.acquired == ["example.com"]
    assert fallback.acquired == []


@pytest.mark.asyncio
async def test_limited_get_falls_back_to_contextvar_limiter() -> None:
    contextvar_limiter = _SpyLimiter()
    client = _StubClient()

    token = current_rate_limiter.set(contextvar_limiter)
    try:
        await limited_get(client, "https://fedlex.data.admin.ch/sparqlendpoint")
    finally:
        current_rate_limiter.reset(token)

    assert contextvar_limiter.acquired == ["fedlex.data.admin.ch"]


class _AlwaysDisallowChecker(RobotsChecker):
    def __init__(self) -> None:
        super().__init__()
        self.checked: list[tuple[str, str]] = []

    async def is_allowed(self, url: str, user_agent: str) -> bool:
        self.checked.append((url, user_agent))
        return False


class _AlwaysAllowChecker(RobotsChecker):
    async def is_allowed(self, url: str, user_agent: str) -> bool:  # noqa: ARG002
        return True


@pytest.mark.asyncio
async def test_strict_robots_blocks_disallowed_url_before_consuming_token() -> None:
    checker = _AlwaysDisallowChecker()
    limiter = _SpyLimiter()
    client = _StubClient()

    robots_token = current_robots_context.set(
        RobotsContext(checker=checker, mode=RobotsMode.STRICT, user_agent="evidara-bot")
    )
    limiter_token = current_rate_limiter.set(limiter)
    try:
        with pytest.raises(RobotsDisallowedError):
            await limited_get(client, "https://example.com/private")
    finally:
        current_rate_limiter.reset(limiter_token)
        current_robots_context.reset(robots_token)

    assert checker.checked == [("https://example.com/private", "evidara-bot")]
    # Critical: no token consumed, no HTTP call made.
    assert limiter.acquired == []
    assert client.calls == []


@pytest.mark.asyncio
async def test_ignore_mode_skips_robots_check() -> None:
    checker = _AlwaysDisallowChecker()
    client = _StubClient()

    robots_token = current_robots_context.set(
        RobotsContext(checker=checker, mode=RobotsMode.IGNORE, user_agent="evidara-bot")
    )
    try:
        response = await limited_get(client, "https://fedlex.data.admin.ch/eli/x")
    finally:
        current_robots_context.reset(robots_token)

    assert response.status_code == 200
    assert checker.checked == []
    assert client.calls == ["https://fedlex.data.admin.ch/eli/x"]


@pytest.mark.asyncio
async def test_strict_robots_allows_when_checker_approves() -> None:
    checker = _AlwaysAllowChecker()
    client = _StubClient()

    robots_token = current_robots_context.set(
        RobotsContext(checker=checker, mode=RobotsMode.STRICT, user_agent="evidara-bot")
    )
    try:
        response = await limited_get(client, "https://example.com/public")
    finally:
        current_robots_context.reset(robots_token)

    assert response.status_code == 200
    assert client.calls == ["https://example.com/public"]
