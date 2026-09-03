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

**Why `protego` and not `urllib.robotparser`.** The stdlib parser predates
RFC 9309 (Robots Exclusion Protocol, September 2022) and disagrees with it in
two directions, both of which matter here because two seeded compliance
policies — `cp_ch_court_decisions` and the municipal tier — run
``robots_mode: strict``:

- **It fails OPEN on wildcards.** ``RuleLine.applies_to`` is a bare
  ``path.startswith``: no ``*``, no ``$``. Measured against a robots.txt
  carrying ``Disallow: /*.pdf$`` and ``Disallow: /*/download``, the stdlib
  parser allows ``/dokumente/urteil.pdf`` and ``/akten/2020/download``;
  ``protego`` refuses both. Those two shapes are how a portal protects bulk
  PDF download, so "strict" was quietly fetching what the site forbade.
- **It fails CLOSED on the ``Allow`` override.** RFC 9309 §2.2.2 makes the
  *longest* matching rule win. The stdlib parser is first-match-in-file-order,
  so ``Disallow: /admin`` followed by ``Allow: /admin/public`` refuses
  ``/admin/public/index.html``. That direction is not a compliance breach —
  it is worse for this platform's purpose, because a permitted path is dropped
  and the operator reads the absence as "the canton disallows us". A refusal
  we invented, presented as the source's, is the confident fabrication
  ADR-0033 exists to prevent.

``protego`` is BSD-3-Clause, has no runtime dependencies, and is maintained by
the Scrapy project as its robots parser. It implements the whole protocol —
wildcards, longest-match, ``Sitemap``, ``Crawl-delay``, ``Request-rate`` — so
there is no hand-rolled remainder here to drift.
"""

from __future__ import annotations

import asyncio
import time
from collections import defaultdict
from collections.abc import Callable
from contextvars import ContextVar
from dataclasses import dataclass
from urllib.parse import urlparse

import httpx
from protego import Protego

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
    parser: Protego | None


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
        transport: httpx.AsyncBaseTransport | None = None,
    ) -> None:
        self.ttl_seconds = ttl_seconds
        self.timeout_seconds = timeout_seconds
        self._monotonic = monotonic
        # Injected only by tests. It exists so a test can drive the REAL
        # `_fetch_and_parse` — the previous test double overrode that method
        # and reimplemented the fetch/status/parse policy inside the test file,
        # so every robots assertion was made against a copy of the code rather
        # than against the code. A parser swap would have gone unnoticed.
        self._transport = transport
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
        # NOTE the argument order: protego is `can_fetch(url, user_agent)`,
        # the stdlib parser was `can_fetch(user_agent, url)`.
        return parser.can_fetch(url, user_agent)

    async def min_interval_seconds(self, url: str, user_agent: str) -> float | None:
        """Smallest gap the site itself asks for between requests, or ``None``.

        Reads BOTH pacing directives a robots.txt can carry and returns the
        stricter of the two, because they say the same thing in different units
        and a site that publishes both means both:

        - ``Crawl-delay: 10`` — at least 10 s between requests.
        - ``Request-rate: 1/5`` — at most 1 request per 5 s, i.e. ``seconds /
          requests`` seconds apart.

        Deliberately parser-agnostic: ``urllib.robotparser`` and ``protego``
        (swapped in #866) expose the same two method names and the same
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

    async def _get_parser(self, origin: str) -> Protego | None:
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
    def _parse(robots_txt: str) -> Protego:
        return Protego.parse(robots_txt)

    async def _fetch_and_parse(self, origin: str) -> Protego | None:
        url = f"{origin}/robots.txt"
        try:
            async with httpx.AsyncClient(
                timeout=self.timeout_seconds, transport=self._transport
            ) as client:
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
