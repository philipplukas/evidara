"""robots.txt compliance for outbound scraping.

:class:`RobotsChecker` fetches and caches robots.txt per host and answers
whether a specific URL is fetchable for a given user agent. Intended to be
consulted inside :func:`limited_get` when the current run's
:class:`CompliancePolicy` declares ``robots_mode=strict``.

Fetches of robots.txt itself bypass the rate limiter — this is meta-traffic
and throttling it would starve the limiter checks that gate real requests.
The checker uses its own short-lived ``httpx`` client.

WHAT ``robots_mode: strict`` ENFORCES
-------------------------------------
Two things, and the second one is new:

1. ``Disallow`` / ``Allow`` — a disallowed URL raises
   :class:`RobotsDisallowedError` before a rate token is spent.
2. ``Crawl-delay`` and ``Request-rate`` — the site's own requested pace, read by
   :meth:`RobotsChecker.min_interval_seconds` and applied per host by
   :meth:`~platform_control.services.politeness.HostRateLimiter.apply_robots_delay`.

Until (2) existed, "strict" meant "obey ``Disallow``", not "obey robots.txt":
neither directive was read anywhere in this repo, so a host asking for ten
seconds between requests was overridden by our own number while the config said
strict. A mode whose name overstates its behaviour is the defect class this repo
keeps fighting, so the name and the behaviour now agree.

The rule is **one-directional**: the site's number may only slow us down. A
``Crawl-delay: 1`` at a host our policy paces at 10 rpm does not license 60 rpm —
robots is a floor on politeness, not a grant.
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


def _call_if_present(parser: object, method: str, user_agent: str) -> object | None:
    """Call ``parser.method(user_agent)``, tolerating absence and parser errors.

    Pacing is advisory: a parser that cannot answer must leave the local policy
    corridor in charge, never block the request. ``is_allowed`` is the directive
    that fails closed; this one does not.
    """
    fn = getattr(parser, method, None)
    if not callable(fn):
        return None
    try:
        return fn(user_agent)
    except Exception:  # pragma: no cover - defensive across parser implementations
        return None


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

    async def min_interval_seconds(self, url: str, user_agent: str) -> float | None:
        """Smallest gap the site itself asks for between requests, or ``None``.

        Reads BOTH pacing directives a robots.txt can carry and returns the
        stricter of the two, because they say the same thing in different units
        and a site that publishes both means both:

        - ``Crawl-delay: 10`` — at least 10 s between requests.
        - ``Request-rate: 1/5`` — at most 1 request per 5 s, i.e. ``seconds /
          requests`` seconds apart.

        Deliberately parser-agnostic: ``urllib.robotparser`` and ``protego``
        (PR #866) expose the same two method names and the same
        ``RequestRate(requests, seconds)`` shape, so this reads whichever parser
        ``_fetch_and_parse`` returned rather than pinning one. A parser that
        offers neither method yields ``None``.

        ``None`` means "the site asked for nothing", NOT "no delay" — the caller
        keeps its own policy pace. See :func:`politeness.limited_get` for the
        one-directional rule this feeds.
        """
        parsed = urlparse(url)
        host = (parsed.hostname or "").lower()
        if not host:
            return None
        origin = f"{parsed.scheme or 'https'}://{host}"
        parser = await self._get_parser(origin)
        if parser is None:
            return None

        candidates: list[float] = []
        delay = _call_if_present(parser, "crawl_delay", user_agent)
        if isinstance(delay, int | float) and delay > 0:
            candidates.append(float(delay))
        rate = _call_if_present(parser, "request_rate", user_agent)
        requests = getattr(rate, "requests", None)
        seconds = getattr(rate, "seconds", None)
        if (
            isinstance(requests, int | float)
            and isinstance(seconds, int | float)
            and requests > 0
            and seconds > 0
        ):
            candidates.append(float(seconds) / float(requests))
        if not candidates:
            return None
        return max(candidates)

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

    def prime(self, origin: str, robots_txt: str) -> None:
        """Seed the cache for ``origin`` with robots.txt text already in hand.

        The one seam that lets a caller (today: tests) supply the bytes without
        supplying the *reading* of them. Everything downstream — which parser,
        how ``Crawl-delay`` is spelled, longest-match — stays production code, so
        a parser swap is still visible to every assertion built on this. A double
        that reimplements the parse asserts against a copy of the code instead.
        """
        self._cache[origin] = _CachedParser(
            expires_at_monotonic=self._monotonic() + self.ttl_seconds,
            parser=self._parse(robots_txt),
        )

    @staticmethod
    def _parse(robots_txt: str) -> RobotFileParser:
        parser = RobotFileParser()
        parser.parse(robots_txt.splitlines())
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
        return self._parse(response.text)


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
