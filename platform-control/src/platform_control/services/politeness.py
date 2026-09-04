"""Per-host politeness primitives.

:class:`HostRateLimiter` bounds outbound traffic to an individual host with an
async token bucket plus a concurrency semaphore. Used by providers that own the
HTTP boundary (today: :mod:`deterministic_http_provider`) to enforce the rate
caps declared by a jurisdiction's :class:`CompliancePolicy`.

The limiter supports a **bounded AIMD corridor**: when a policy declares
``min_requests_per_minute_per_host`` and ``start_requests_per_minute_per_host``
the effective rate starts at ``start`` and climbs toward ``max`` (additive
increase, +1 rpm per ``increase_interval_seconds`` of clean traffic) or drops
toward ``min`` on pressure (multiplicative decrease: halve on 429 / 503 /
connection error). ``Retry-After`` headers pause acquisition exactly that long.

When min/start are left as ``None`` the corridor collapses to ``max`` on all
three points — equivalent to the original static cap.

On top of that corridor sits the pace the HOST asked for. Under
``robots_mode: strict``, a ``Crawl-delay`` or ``Request-rate`` in the site's
robots.txt is pushed in per host via :meth:`HostRateLimiter.apply_robots_delay`
and can only *lower* the effective rate. Our corridor is what we are willing to
send; the robots directive is what they are willing to receive, and the smaller
of the two wins.

Firecrawl delegates politeness to the external service, so its provider is
deliberately not wired to this limiter — double-budgeting would be misleading.
"""

from __future__ import annotations

import asyncio
import math
import time
from collections import defaultdict
from collections.abc import Callable
from contextvars import ContextVar
from dataclasses import dataclass
from datetime import UTC, datetime
from email.utils import parsedate_to_datetime
from typing import Any
from urllib.parse import urlparse

import httpx

# Status codes that unambiguously signal "back off": rate limit, service
# unavailable, gateway timeout, and Cloudflare's retry-friendly variants.
_PRESSURE_STATUSES: frozenset[int] = frozenset({429, 503, 504, 522, 524})


@dataclass(slots=True)
class HostBudget:
    """Per-host state: current token count + last-refill timestamp + semaphore.

    ``robots_min_interval_seconds`` is the gap the HOST asked for in its
    robots.txt (``Crawl-delay`` / ``Request-rate``), or ``None`` when it asked
    for nothing. It is per-host rather than per-policy because one policy can
    govern several hosts and each publishes its own file.
    """

    tokens: float
    last_refill_monotonic: float
    semaphore: asyncio.Semaphore
    robots_min_interval_seconds: float | None = None
    # When the last permit for this host was GRANTED. `last_refill_monotonic`
    # cannot stand in for it: refills happen on every acquire attempt, including
    # the ones that then went to sleep waiting.
    last_granted_monotonic: float | None = None


class HostRateLimiter:
    """Token-bucket rate limiter keyed by host, with optional AIMD adaptation.

    Each host gets a refilling token bucket sized by the current effective rate
    plus a concurrency semaphore. :meth:`acquire` waits until a token is
    available and concurrency is below ``max_concurrent``. Callers must release
    via the async context manager that :meth:`acquire` returns so the
    concurrency cap decrements even on errors.

    :meth:`observe` is the feedback seam for the AIMD controller. Call it from
    :func:`limited_get` after each outbound request so a clean 2xx climbs the
    rate and a 429/503 halves it.
    """

    def __init__(
        self,
        *,
        max_requests_per_minute: int = 60,
        max_concurrent: int = 2,
        min_requests_per_minute: int | None = None,
        start_requests_per_minute: int | None = None,
        increase_interval_seconds: float = 60.0,
        monotonic: Callable[[], float] = time.monotonic,
    ) -> None:
        if max_requests_per_minute <= 0:
            raise ValueError("max_requests_per_minute must be > 0")
        if max_concurrent <= 0:
            raise ValueError("max_concurrent must be > 0")
        if increase_interval_seconds <= 0:
            raise ValueError("increase_interval_seconds must be > 0")

        resolved_min = (
            max_requests_per_minute if min_requests_per_minute is None else min_requests_per_minute
        )
        resolved_start = (
            max_requests_per_minute
            if start_requests_per_minute is None
            else start_requests_per_minute
        )
        if resolved_min <= 0:
            raise ValueError("min_requests_per_minute must be > 0")
        if resolved_min > max_requests_per_minute:
            raise ValueError("min_requests_per_minute must be <= max_requests_per_minute")
        if resolved_start < resolved_min or resolved_start > max_requests_per_minute:
            raise ValueError("start_requests_per_minute must fall within [min, max]")

        self.max_requests_per_minute = max_requests_per_minute
        self.min_requests_per_minute = resolved_min
        self.max_concurrent = max_concurrent
        self.increase_interval_seconds = increase_interval_seconds
        self._current_rpm: float = float(resolved_start)
        self._budgets: dict[str, HostBudget] = {}
        self._locks: dict[str, asyncio.Lock] = defaultdict(asyncio.Lock)
        self._monotonic = monotonic
        self._last_increase_monotonic: float = monotonic()
        self._retry_after_deadline: float = 0.0

    @property
    def adaptive(self) -> bool:
        """True when the corridor has room to probe (start < max or min < max)."""
        return (
            self._current_rpm < self.max_requests_per_minute
            or self.min_requests_per_minute < self.max_requests_per_minute
        )

    @property
    def current_requests_per_minute(self) -> float:
        return self._current_rpm

    def _refill_rate_per_second(self) -> float:
        return self._current_rpm / 60.0

    def apply_robots_delay(self, host: str, min_interval_seconds: float | None) -> None:
        """Record the minimum gap ``host``'s own robots.txt asked for between requests.

        One-directional, and that is the whole contract: this may only make the
        limiter slower. ``Crawl-delay: 1`` at a host whose policy paces at 6 rpm
        does not license 60 rpm — robots.txt is a floor on politeness, not a
        grant of one. It is enforced as a *gate* alongside the token bucket, not
        as a second rate: whichever of the two is slower decides when the next
        request goes out.

        A gate rather than a rate because the two say different things. The
        bucket bounds an average and tolerates a burst against it; ``Crawl-delay:
        10`` is a statement about the gap between *consecutive* requests, which a
        bucket holding ten tokens satisfies on average and violates immediately.

        Called from :func:`limited_get` once the robots context is known.
        ``None`` (the site asked for nothing) clears any previous gap rather than
        pinning a stale one, since robots.txt can change within a process
        lifetime and the checker's cache has a TTL. A non-positive value is not a
        pace and is treated as ``None``.
        """
        if min_interval_seconds is not None and min_interval_seconds <= 0:
            min_interval_seconds = None
        self._get_budget(host).robots_min_interval_seconds = min_interval_seconds

    def _robots_gate_wait(self, budget: HostBudget, now: float) -> float:
        """Seconds still owed to the host's declared gap, or 0.0 when none is."""
        interval = budget.robots_min_interval_seconds
        if interval is None or budget.last_granted_monotonic is None:
            return 0.0
        return max(0.0, budget.last_granted_monotonic + interval - now)

    def _get_budget(self, host: str) -> HostBudget:
        budget = self._budgets.get(host)
        if budget is None:
            budget = HostBudget(
                tokens=float(self._current_rpm),
                last_refill_monotonic=self._monotonic(),
                semaphore=asyncio.Semaphore(self.max_concurrent),
            )
            self._budgets[host] = budget
        return budget

    def _refill(self, budget: HostBudget) -> None:
        now = self._monotonic()
        elapsed = max(0.0, now - budget.last_refill_monotonic)
        budget.tokens = min(
            float(self.max_requests_per_minute),
            budget.tokens + elapsed * self._refill_rate_per_second(),
        )
        budget.last_refill_monotonic = now

    async def acquire(self, host: str) -> _HostPermit:
        """Block until a token and a concurrency slot are available for ``host``.

        If ``Retry-After`` was observed, the call sleeps until the deadline
        elapses before consulting the bucket. Concurrency is acquired first so
        the semaphore correctly bounds in-flight work regardless of token wait.
        """
        budget = self._get_budget(host)
        await budget.semaphore.acquire()
        try:
            retry_wait = self._retry_after_deadline - self._monotonic()
            if retry_wait > 0:
                await asyncio.sleep(retry_wait)
            while True:
                async with self._locks[host]:
                    now = self._monotonic()
                    # The host's own declared gap, checked alongside the bucket.
                    # Whichever of the two is slower decides when this goes out.
                    wait_seconds = self._robots_gate_wait(budget, now)
                    if wait_seconds <= 0.0:
                        self._refill(budget)
                        if budget.tokens >= 1.0:
                            budget.tokens -= 1.0
                            budget.last_granted_monotonic = now
                            return _HostPermit(semaphore=budget.semaphore)
                        refill_rate = self._refill_rate_per_second()
                        if refill_rate <= 0:
                            # Defensive: shouldn't happen given validation, but
                            # would otherwise divide by zero.
                            wait_seconds = 1.0
                        else:
                            deficit = 1.0 - budget.tokens
                            wait_seconds = deficit / refill_rate
                await asyncio.sleep(wait_seconds)
        except BaseException:
            budget.semaphore.release()
            raise

    def observe(
        self,
        *,
        status: int | None = None,
        exception: BaseException | None = None,
        retry_after_seconds: float | None = None,
    ) -> None:
        """Feed the outcome of a request back into the AIMD controller.

        - Success (2xx/3xx, no exception) → additive increase one rpm per
          ``increase_interval_seconds`` of clean traffic, capped at ``max``.
        - Pressure (429 / 503 / 504 / 522 / 524 / exception) → multiplicative
          decrease: halve ``current_rpm``, floored at ``min``. ``retry_after``
          sets a hard no-acquire window until the deadline elapses.
        - Other statuses (4xx except 429, etc.) are a no-op; client-side
          failures shouldn't change the server-side politeness budget.
        """
        now = self._monotonic()

        if exception is not None or (status is not None and status in _PRESSURE_STATUSES):
            halved = max(float(self.min_requests_per_minute), self._current_rpm / 2.0)
            self._current_rpm = halved
            # Reset the increase clock so we don't immediately climb again.
            self._last_increase_monotonic = now
            if retry_after_seconds is not None and retry_after_seconds > 0:
                self._retry_after_deadline = max(
                    self._retry_after_deadline, now + retry_after_seconds
                )
            return

        if status is not None and 200 <= status < 400:
            if self._current_rpm >= self.max_requests_per_minute:
                return
            if now - self._last_increase_monotonic < self.increase_interval_seconds:
                return
            self._current_rpm = min(
                float(self.max_requests_per_minute),
                self._current_rpm + 1.0,
            )
            self._last_increase_monotonic = now


class _HostPermit:
    """Released either via ``async with`` or by an explicit ``release()`` call."""

    __slots__ = ("_semaphore", "_released")

    def __init__(self, semaphore: asyncio.Semaphore) -> None:
        self._semaphore = semaphore
        self._released = False

    def release(self) -> None:
        if not self._released:
            self._semaphore.release()
            self._released = True

    async def __aenter__(self) -> _HostPermit:
        return self

    async def __aexit__(self, exc_type, exc, tb) -> None:
        self.release()


current_rate_limiter: ContextVar[HostRateLimiter | None] = ContextVar(
    "current_rate_limiter", default=None
)
"""Run-scoped limiter set by ``run_service`` before dispatch and read by each
provider's outbound GET. Propagates across ``await`` points automatically."""


def _parse_retry_after(header_value: str | None, *, now: datetime | None = None) -> float | None:
    """Parse a ``Retry-After`` header as seconds. ``None`` when absent or unparseable.

    RFC 9110 §10.2.3 defines **two** forms — ``delay-seconds`` and ``HTTP-date``
    — and a server is free to choose either. This used to handle only the first
    and returned ``None`` for the second, documented at the time as "rare in
    scraping scenarios". That was a fail-open on the one signal a host sends to
    say *exactly* how long to stay away: the AIMD halving still applied, but the
    explicit pause the host asked for was dropped on the floor. The date form is
    what a server emits when the window is a wall-clock moment rather than a
    duration (a maintenance window, a daily quota reset), which is precisely the
    public-sector portal case.

    ``email.utils.parsedate_to_datetime`` is the stdlib's RFC 5322/9110 date
    parser and covers all three date formats the spec permits, so nothing is
    hand-rolled here and there is no second reading to drift.

    ``now`` is injectable so the conversion is testable without freezing the
    clock; it defaults to the current UTC instant.
    """
    if header_value is None:
        return None
    stripped = header_value.strip()
    if not stripped:
        return None

    try:
        seconds = float(stripped)
    except ValueError:
        pass
    else:
        # `float()` happily accepts "inf" and "nan". An infinite deadline would
        # pause this host forever with no way back short of a restart, so a
        # non-finite delay is treated as no delay at all.
        return max(0.0, seconds) if math.isfinite(seconds) else None

    try:
        deadline = parsedate_to_datetime(stripped)
    except (TypeError, ValueError):
        return None
    if deadline is None:  # pragma: no cover — defensive, older stdlib returned None
        return None
    # An HTTP-date is always GMT; a value that arrives naive is read as UTC
    # rather than as local time, which would shift the pause by the offset.
    if deadline.tzinfo is None:
        deadline = deadline.replace(tzinfo=UTC)
    reference = now if now is not None else datetime.now(UTC)
    if reference.tzinfo is None:
        reference = reference.replace(tzinfo=UTC)
    # A date already in the past means "you may retry now", not "retry in the
    # negative"; clamping keeps that from becoming an immediate-resume bug.
    return max(0.0, (deadline - reference).total_seconds())


async def limited_get(
    client: httpx.AsyncClient,
    url: str,
    *,
    limiter: HostRateLimiter | None = None,
    **kwargs: Any,
) -> httpx.Response:
    """GET ``url`` through the effective rate limiter + robots check for the current run.

    Resolution order for the limiter: explicit ``limiter`` → ``current_rate_limiter``
    contextvar → no limiter (bypass). The robots check is driven only by
    ``current_robots_context`` — when present and ``mode=strict``, a disallowed
    URL raises :class:`RobotsDisallowedError` *before* any token is consumed,
    so robots blocks never deplete the rate budget.

    ``strict`` also honours the site's ``Crawl-delay`` / ``Request-rate``: the
    declared interval is pushed into the limiter for that host before the token
    is taken, so the next request already waits for it. It only ever slows the
    limiter — a site asking for less delay than our policy applies does not
    raise our rate. A ``strict`` policy with no limiter (which the dispatch path
    now refuses — see ``CompliancePolicyMissingError``) has nowhere to apply the
    delay, so the pace is dropped; the ``Disallow`` check still runs.

    After each request the response (or exception) is fed back to the limiter
    via :meth:`HostRateLimiter.observe` so the AIMD corridor moves in response
    to the target server's behaviour.

    Providers that own their HTTP boundary (deterministic, fedlex, ris) call this
    in place of ``client.get`` so the per-jurisdiction :class:`CompliancePolicy`
    is honoured without each provider needing its own integration code.
    """
    # Local import to avoid a circular import via services/robots.py if it later
    # needs anything from politeness. The modules are independent today.
    from platform_control.domain import RobotsMode
    from platform_control.services.robots import (
        RobotsDisallowedError,
        current_robots_context,
    )

    effective = limiter if limiter is not None else current_rate_limiter.get()
    host = (urlparse(url).hostname or "").lower()

    robots_ctx = current_robots_context.get()
    if robots_ctx is not None and robots_ctx.mode is RobotsMode.STRICT:
        allowed = await robots_ctx.checker.is_allowed(url, robots_ctx.user_agent)
        if not allowed:
            raise RobotsDisallowedError(url)
        # The site's own requested pace, applied before the token is taken so
        # the very next acquire already honours it. The checker caches
        # robots.txt per origin, so this costs no extra fetch. `strict` used to
        # mean "obey Disallow" only; this is the half that makes the mode's name
        # true. It can only slow the limiter down — see `apply_robots_delay`.
        if effective is not None and host:
            effective.apply_robots_delay(
                host,
                await robots_ctx.checker.min_interval_seconds(url, robots_ctx.user_agent),
            )

    if effective is None:
        return await client.get(url, **kwargs)
    async with await effective.acquire(host):
        try:
            response = await client.get(url, **kwargs)
        except BaseException as exc:
            effective.observe(exception=exc)
            raise
        retry_after = _parse_retry_after(response.headers.get("retry-after"))
        effective.observe(status=response.status_code, retry_after_seconds=retry_after)
        return response
