"""robots.txt compliance for outbound scraping.

:class:`RobotsChecker` fetches and caches robots.txt per host and answers
whether a specific URL is fetchable for a given user agent. Intended to be
consulted inside :func:`limited_get` when the current run's
:class:`CompliancePolicy` declares ``robots_mode=strict``.

Fetches of robots.txt itself bypass the rate limiter — this is meta-traffic
and throttling it would starve the limiter checks that gate real requests.
The checker uses its own short-lived ``httpx`` client.
"""

from __future__ import annotations

import asyncio
import time
from collections import defaultdict
from collections.abc import Callable
from contextvars import ContextVar
from dataclasses import dataclass
from urllib.parse import urlparse
from urllib.robotparser import RobotFileParser

import httpx

from platform_control.domain import RobotsMode


class RobotsDisallowedError(Exception):
    """Raised when robots.txt disallows fetching a URL under the current policy."""

    def __init__(self, url: str) -> None:
        super().__init__(f"robots.txt disallows {url}")
        self.url = url


@dataclass(slots=True)
class _CachedParser:
    expires_at_monotonic: float
    parser: RobotFileParser | None


class RobotsChecker:
    """Per-host robots.txt cache with a short TTL.

    ``is_allowed`` returns ``True`` when there is no robots.txt, when the
    origin returns a 4xx for ``/robots.txt`` (the standard "no policy" signal),
    or when the parsed file grants the caller's user agent. A 5xx or network
    error is treated as *allowed* to match the common robots interpretation
    that upstream faults must not become a silent crawl block; operators who
    want to fail-closed on outage can layer that check above this class.
    """

    def __init__(
        self,
        *,
        ttl_seconds: int = 3600,
        timeout_seconds: float = 10.0,
        monotonic: Callable[[], float] = time.monotonic,
    ) -> None:
        self.ttl_seconds = ttl_seconds
        self.timeout_seconds = timeout_seconds
        self._monotonic = monotonic
        self._cache: dict[str, _CachedParser] = {}
        self._locks: dict[str, asyncio.Lock] = defaultdict(asyncio.Lock)

    async def is_allowed(self, url: str, user_agent: str) -> bool:
        parsed = urlparse(url)
        host = (parsed.hostname or "").lower()
        scheme = parsed.scheme or "https"
        if not host:
            return True
        origin = f"{scheme}://{host}"
        parser = await self._get_parser(origin)
        if parser is None:
            return True
        return parser.can_fetch(user_agent, url)

    async def _get_parser(self, origin: str) -> RobotFileParser | None:
        async with self._locks[origin]:
            cached = self._cache.get(origin)
            now = self._monotonic()
            if cached is not None and cached.expires_at_monotonic > now:
                return cached.parser
            parser = await self._fetch_and_parse(origin)
            self._cache[origin] = _CachedParser(
                expires_at_monotonic=now + self.ttl_seconds,
                parser=parser,
            )
            return parser

    async def _fetch_and_parse(self, origin: str) -> RobotFileParser | None:
        url = f"{origin}/robots.txt"
        try:
            async with httpx.AsyncClient(timeout=self.timeout_seconds) as client:
                response = await client.get(url)
        except httpx.HTTPError:
            return None
        if response.status_code >= 500:
            return None
        if response.status_code >= 400:
            return None
        parser = RobotFileParser()
        parser.parse(response.text.splitlines())
        return parser


@dataclass(slots=True)
class RobotsContext:
    """Per-run politeness envelope for robots enforcement.

    Emitted by ``run_service`` before dispatch. ``mode`` controls enforcement;
    ``IGNORE`` short-circuits the check entirely for sources on open-data
    programmes (Fedlex, RIS OGD) where scraping is explicitly authorised.
    """

    checker: RobotsChecker
    mode: RobotsMode
    user_agent: str


current_robots_context: ContextVar[RobotsContext | None] = ContextVar(
    "current_robots_context", default=None
)
"""Run-scoped robots context read by ``limited_get``. Parallel to
``current_rate_limiter`` — both are set by ``run_service._dispatch_run`` around
``provider.start_run``."""
