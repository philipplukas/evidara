"""Per-host politeness primitives.

:class:`HostRateLimiter` bounds outbound traffic to an individual host with an
async token bucket plus a concurrency semaphore. Used by providers that own the
HTTP boundary (today: :mod:`deterministic_http_provider`) to enforce the rate
caps declared by a jurisdiction's :class:`CompliancePolicy`.

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


@dataclass(slots=True)
class HostBudget:
    """Per-host state: current token count + last-refill timestamp + semaphore."""

    tokens: float
    last_refill_monotonic: float
    semaphore: asyncio.Semaphore


class HostRateLimiter:
    """Token-bucket rate limiter keyed by host.

    Each host gets ``max_requests_per_minute`` tokens that refill continuously;
    :meth:`acquire` waits until a token is available and concurrency is below
    ``max_concurrent``. Callers must release via the async context manager that
    :meth:`acquire` returns, so the concurrency cap decrements even on errors.
    """

    def __init__(
        self,
        *,
        max_requests_per_minute: int = 60,
        max_concurrent: int = 2,
        monotonic: Callable[[], float] = time.monotonic,
    ) -> None:
        if max_requests_per_minute <= 0:
            raise ValueError("max_requests_per_minute must be > 0")
        if max_concurrent <= 0:
            raise ValueError("max_concurrent must be > 0")
        self.max_requests_per_minute = max_requests_per_minute
        self.max_concurrent = max_concurrent
        self._refill_rate_per_second = max_requests_per_minute / 60.0
        self._budgets: dict[str, HostBudget] = {}
        self._locks: dict[str, asyncio.Lock] = defaultdict(asyncio.Lock)
        self._monotonic = monotonic

    def _get_budget(self, host: str) -> HostBudget:
        budget = self._budgets.get(host)
        if budget is None:
            budget = HostBudget(
                tokens=float(self.max_requests_per_minute),
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
            budget.tokens + elapsed * self._refill_rate_per_second,
        )
        budget.last_refill_monotonic = now

    async def acquire(self, host: str) -> _HostPermit:
        """Block until a token and a concurrency slot are available for ``host``."""
        budget = self._get_budget(host)
        await budget.semaphore.acquire()
        try:
            while True:
                async with self._locks[host]:
                    self._refill(budget)
                    if budget.tokens >= 1.0:
                        budget.tokens -= 1.0
                        return _HostPermit(semaphore=budget.semaphore)
                    deficit = 1.0 - budget.tokens
                    wait_seconds = deficit / self._refill_rate_per_second
                await asyncio.sleep(wait_seconds)
        except BaseException:
            budget.semaphore.release()
            raise


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
        return await client.get(url, **kwargs)
