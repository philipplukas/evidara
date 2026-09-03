from __future__ import annotations

import httpx
import pytest

from platform_control.services.robots import RobotsChecker, _CachedParser


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

    assert await checker.is_allowed("https://example.com/private/secret", "evidara-bot") is False
    assert await checker.is_allowed("https://example.com/public/page", "evidara-bot") is True


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


# --- Crawl-delay / Request-rate ------------------------------------------
#
# Neither directive was read anywhere in this repo before these tests existed
# (verified by grep: zero occurrences of either string outside vendored code),
# while two seeded policies declared `robots_mode: strict`. "Strict" meant
# "obey Disallow", not "obey robots.txt".
#
# `prime()` supplies the robots.txt BYTES and nothing else — the parse is
# production code, so these assertions still hold the parser rather than a copy
# of it.


@pytest.mark.asyncio
@pytest.mark.parametrize(
    ("robots_body", "expected"),
    [
        # Nothing declared: the site asked for nothing. `None` means "keep your
        # own pace", NOT "no delay" — see limited_get.
        ("User-agent: *\nAllow: /\n", None),
        # Crawl-delay alone.
        ("User-agent: *\nCrawl-delay: 10\n", 10.0),
        # Request-rate alone: 1 request per 5 s => 5 s apart.
        ("User-agent: *\nRequest-rate: 1/5\n", 5.0),
        # 2 requests per 10 s is also 5 s apart, not 10.
        ("User-agent: *\nRequest-rate: 2/10\n", 5.0),
        # Both declared: the STRICTER wins. A site that publishes both means
        # both, and honouring only the smaller would out-pace one of them.
        ("User-agent: *\nCrawl-delay: 30\nRequest-rate: 1/5\n", 30.0),
        ("User-agent: *\nCrawl-delay: 2\nRequest-rate: 1/20\n", 20.0),
        # Zero is not a pace; it must not become a delay floor of 0 that the
        # limiter then treats as "robots is pacing this host".
        ("User-agent: *\nCrawl-delay: 0\n", None),
    ],
)
async def test_min_interval_seconds_reads_both_pacing_directives(
    robots_body: str, expected: float | None
) -> None:
    checker = RobotsChecker()
    checker.prime("https://example.ch", robots_body)

    assert await checker.min_interval_seconds("https://example.ch/a", "evidara-bot") == expected


@pytest.mark.asyncio
async def test_min_interval_seconds_is_none_when_there_is_no_robots_file() -> None:
    """No robots.txt is not a slow-down instruction; the local corridor stays in charge."""
    checker = _ClockedChecker(_transport_for({}))  # default 404

    assert await checker.min_interval_seconds("https://example.ch/a", "evidara-bot") is None


@pytest.mark.asyncio
async def test_min_interval_seconds_ignores_a_url_without_a_host() -> None:
    checker = RobotsChecker()

    assert await checker.min_interval_seconds("/nohost", "evidara-bot") is None


@pytest.mark.asyncio
async def test_a_parser_that_cannot_answer_does_not_block_the_request() -> None:
    """Pacing is advisory: only `Disallow` fails closed.

    `min_interval_seconds` is deliberately duck-typed across parsers (the repo is
    mid-swap from `urllib.robotparser` to `protego`, PR #866 — both expose these
    two methods). A parser offering neither must yield "no opinion", not an
    exception that would take down an otherwise-permitted fetch.
    """

    class _MuteParser:
        pass

    checker = RobotsChecker()
    checker._cache["https://example.ch"] = _CachedParser(
        expires_at_monotonic=float("inf"), parser=_MuteParser()
    )

    assert await checker.min_interval_seconds("https://example.ch/a", "evidara-bot") is None
