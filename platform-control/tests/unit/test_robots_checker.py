from __future__ import annotations

import httpx
import pytest

from platform_control.services.robots import RobotsChecker, _CachedParser


def _transport_for(response_map: dict[str, tuple[int, str]]) -> httpx.MockTransport:
    def handler(request: httpx.Request) -> httpx.Response:
        status, body = response_map.get(str(request.url), (404, ""))
        return httpx.Response(status, text=body)

    return httpx.MockTransport(handler)


def _checker_for(response_map: dict[str, tuple[int, str]], **kwargs) -> RobotsChecker:
    """A checker whose robots.txt fetch is mocked but whose parse is production code.

    The transport is injected rather than `_fetch_and_parse` being overridden.
    The previous double overrode that method and reimplemented the status-code
    policy and the parse inside this file, so none of these assertions touched
    `RobotsChecker`'s own parsing at all.
    """
    return RobotsChecker(transport=_transport_for(response_map), **kwargs)


@pytest.mark.asyncio
async def test_allows_when_no_robots_file() -> None:
    checker = _checker_for({})  # default 404 for robots.txt

    allowed = await checker.is_allowed("https://example.com/page", "evidara-bot")

    assert allowed is True


@pytest.mark.asyncio
async def test_respects_disallow_rule_for_user_agent() -> None:
    robots_body = "User-agent: *\nDisallow: /private/\n"
    checker = _checker_for({"https://example.com/robots.txt": (200, robots_body)})

    assert await checker.is_allowed("https://example.com/private/secret", "evidara-bot") is False
    assert await checker.is_allowed("https://example.com/public/page", "evidara-bot") is True


@pytest.mark.asyncio
async def test_allows_on_server_error() -> None:
    checker = _checker_for({"https://example.com/robots.txt": (503, "unavailable")})

    allowed = await checker.is_allowed("https://example.com/anything", "evidara-bot")

    assert allowed is True


@pytest.mark.asyncio
async def test_caches_per_origin() -> None:
    call_count = 0

    def handler(request: httpx.Request) -> httpx.Response:
        nonlocal call_count
        call_count += 1
        return httpx.Response(200, text="User-agent: *\nAllow: /\n")

    checker = RobotsChecker(transport=httpx.MockTransport(handler))

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

# --- RFC 9309 conformance -------------------------------------------------
#
# Each case below is answered WRONGLY by `urllib.robotparser`, which this module
# used until protego was adopted. They are the reason for the swap, not a
# restatement of protego's own test suite: the first two are a compliance
# breach (we fetch what the site forbids), the third is a self-inflicted
# refusal reported to the operator as the source's.

_WILDCARD_ROBOTS = """User-agent: *
Disallow: /*.pdf$
Disallow: /*/download
Disallow: /admin
Allow: /admin/public
"""


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
    checker = _checker_for({})  # unmapped URL -> 404

    assert await checker.min_interval_seconds("https://example.ch/a", "evidara-bot") is None


@pytest.mark.asyncio
async def test_min_interval_seconds_ignores_a_url_without_a_host() -> None:
    checker = RobotsChecker()

    assert await checker.min_interval_seconds("/nohost", "evidara-bot") is None


@pytest.mark.asyncio
async def test_a_parser_that_cannot_answer_does_not_block_the_request() -> None:
    """Pacing is advisory: only `Disallow` fails closed.

    `min_interval_seconds` is deliberately duck-typed across parsers (the repo
    swapped `urllib.robotparser` for `protego` in #866 — both expose these two
    methods). A parser offering neither must yield "no opinion", not an
    exception that would take down an otherwise-permitted fetch.
    """

    class _MuteParser:
        pass

    checker = RobotsChecker()
    checker._cache["https://example.ch"] = _CachedParser(
        expires_at_monotonic=float("inf"), parser=_MuteParser()
    )

    assert await checker.min_interval_seconds("https://example.ch/a", "evidara-bot") is None


@pytest.mark.asyncio
@pytest.mark.parametrize(
    ("url", "expected"),
    [
        # `Disallow: /*.pdf$` — stdlib startswith() matched nothing and allowed
        # this. It is how a portal protects bulk PDF download.
        ("https://example.ch/dokumente/urteil.pdf", False),
        # The `$` anchor must not swallow a non-PDF sibling.
        ("https://example.ch/dokumente/urteil.html", True),
        # Mid-path `*`. Same stdlib fail-open.
        ("https://example.ch/akten/2020/download", False),
        # Longest-match wins (RFC 9309 §2.2.2): `Allow: /admin/public` overrides
        # the earlier `Disallow: /admin`. The stdlib parser is first-match and
        # refused this — dropping a permitted path and letting the operator read
        # the gap as the source's refusal.
        ("https://example.ch/admin/public/index.html", True),
        # ...but the un-overridden prefix stays disallowed.
        ("https://example.ch/admin/secret", False),
    ],
)
async def test_rfc9309_wildcards_and_longest_match(url: str, expected: bool) -> None:
    checker = _checker_for({"https://example.ch/robots.txt": (200, _WILDCARD_ROBOTS)})

    assert await checker.is_allowed(url, "evidara-bot") is expected


@pytest.mark.asyncio
async def test_specific_user_agent_group_overrides_wildcard_group() -> None:
    """A group naming our UA replaces the `*` group outright — it does not merge."""
    robots_body = "User-agent: *\nDisallow: /\n\nUser-agent: evidara-bot\nAllow: /\n"
    checker = _checker_for({"https://example.ch/robots.txt": (200, robots_body)})

    assert await checker.is_allowed("https://example.ch/anything", "evidara-bot") is True
    assert await checker.is_allowed("https://example.ch/anything", "other-bot") is False
