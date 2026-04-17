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

Firecrawl delegates politeness to the external service, so its provider is
deliberately not wired to this limiter — double-budgeting would be misleading.
"""

from __future__ import annotations

import asyncio
import time
from collections import defaultdict
from collections.abc import Callable
from contextvars import ContextVar
from dataclasses import dataclass
from typing import Any
from urllib.parse import urlparse

import httpx

# Status codes that unambiguously signal "back off": rate limit, service
# unavailable, gateway timeout, and Cloudflare's retry-friendly variants.
_PRESSURE_STATUSES: frozenset[int] = frozenset({429, 503, 504, 522, 524})


@dataclass(slots=True)
class HostBudget:
    """Per-host state: current token count + last-refill timestamp + semaphore."""

    tokens: float
    last_refill_monotonic: float
    semaphore: asyncio.Semaphore


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
                    self._refill(budget)
                    if budget.tokens >= 1.0:
                        budget.tokens -= 1.0
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


def _parse_retry_after(header_value: str | None) -> float | None:
    """Parse a ``Retry-After`` header as seconds. Returns ``None`` when absent
    or when the value is an HTTP-date we can't trivially convert.

    Seconds parsing is what real operators observe; HTTP-date is rare in
    scraping scenarios and we fail-open by returning ``None`` so the caller's
    AIMD halving still applies but no explicit pause is scheduled.
    """
    if header_value is None:
        return None
    stripped = header_value.strip()
    if not stripped:
        return None
    try:
        seconds = float(stripped)
    except ValueError:
        return None
    return max(0.0, seconds)


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

    robots_ctx = current_robots_context.get()
    if robots_ctx is not None and robots_ctx.mode is RobotsMode.STRICT:
        allowed = await robots_ctx.checker.is_allowed(url, robots_ctx.user_agent)
        if not allowed:
            raise RobotsDisallowedError(url)

    effective = limiter if limiter is not None else current_rate_limiter.get()
    if effective is None:
        return await client.get(url, **kwargs)
    host = (urlparse(url).hostname or "").lower()
    async with await effective.acquire(host):
        try:
            response = await client.get(url, **kwargs)
        except BaseException as exc:
            effective.observe(exception=exc)
            raise
        retry_after = _parse_retry_after(response.headers.get("retry-after"))
        effective.observe(status=response.status_code, retry_after_seconds=retry_after)
        return response
