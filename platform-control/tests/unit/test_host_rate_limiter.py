from __future__ import annotations

import asyncio

import pytest

from platform_control.services.politeness import HostRateLimiter


class _FakeClock:
    """Monotonic clock surrogate the limiter polls via its ``monotonic`` hook."""

    def __init__(self) -> None:
        self.now = 0.0

    def __call__(self) -> float:
        return self.now

    def advance(self, seconds: float) -> None:
        self.now += seconds


def test_rejects_non_positive_config() -> None:
    with pytest.raises(ValueError):
        HostRateLimiter(max_requests_per_minute=0)
    with pytest.raises(ValueError):
        HostRateLimiter(max_concurrent=0)


@pytest.mark.asyncio
async def test_initial_bucket_is_full(monkeypatch: pytest.MonkeyPatch) -> None:
    clock = _FakeClock()
    limiter = HostRateLimiter(max_requests_per_minute=60, max_concurrent=5, monotonic=clock)

    async def _never_sleep(_seconds: float) -> None:
        raise AssertionError("initial bucket should not require sleep")

    monkeypatch.setattr(asyncio, "sleep", _never_sleep)

    for _ in range(60):
        permit = await limiter.acquire("example.com")
        permit.release()


@pytest.mark.asyncio
async def test_exhaustion_waits_for_refill() -> None:
    clock = _FakeClock()
    sleeps: list[float] = []

    async def _record_sleep(seconds: float) -> None:
        sleeps.append(seconds)
        clock.advance(seconds)

    limiter = HostRateLimiter(max_requests_per_minute=60, max_concurrent=10, monotonic=clock)
    # Drain the bucket fully.
    for _ in range(60):
        permit = await limiter.acquire("example.com")
        permit.release()

    # Next acquire must wait for ~1 second (60 rpm = 1 token per second).
    import platform_control.services.politeness as politeness

    original_sleep = asyncio.sleep
    politeness.asyncio.sleep = _record_sleep  # type: ignore[assignment]
    try:
        permit = await limiter.acquire("example.com")
    finally:
        politeness.asyncio.sleep = original_sleep  # type: ignore[assignment]
    permit.release()

    assert sleeps, "expected acquire() to sleep when bucket empty"
    assert sleeps[0] == pytest.approx(1.0, rel=0.05)


@pytest.mark.asyncio
async def test_distinct_hosts_do_not_share_budget() -> None:
    clock = _FakeClock()
    limiter = HostRateLimiter(max_requests_per_minute=60, max_concurrent=5, monotonic=clock)
    # Drain host A fully.
    for _ in range(60):
        permit = await limiter.acquire("a.example")
        permit.release()
    # Host B still has a full bucket; acquire must not sleep.
    import platform_control.services.politeness as politeness

    calls: list[float] = []

    async def _record_sleep(seconds: float) -> None:
        calls.append(seconds)
        clock.advance(seconds)

    original_sleep = asyncio.sleep
    politeness.asyncio.sleep = _record_sleep  # type: ignore[assignment]
    try:
        permit = await limiter.acquire("b.example")
    finally:
        politeness.asyncio.sleep = original_sleep  # type: ignore[assignment]
    permit.release()

    assert calls == []


@pytest.mark.asyncio
async def test_concurrent_acquires_are_bounded_by_semaphore() -> None:
    clock = _FakeClock()
    limiter = HostRateLimiter(max_requests_per_minute=600, max_concurrent=2, monotonic=clock)

    permit_a = await limiter.acquire("x.example")
    permit_b = await limiter.acquire("x.example")

    third = asyncio.create_task(limiter.acquire("x.example"))
    # Yield once so the task runs up to the semaphore acquire.
    await asyncio.sleep(0)

    assert not third.done()

    permit_a.release()
    permit = await third
    permit.release()
    permit_b.release()


def test_corridor_validation_rejects_inverted_bounds() -> None:
    with pytest.raises(ValueError):
        HostRateLimiter(
            max_requests_per_minute=60,
            min_requests_per_minute=120,  # > max
            start_requests_per_minute=60,
        )
    with pytest.raises(ValueError):
        HostRateLimiter(
            max_requests_per_minute=60,
            min_requests_per_minute=30,
            start_requests_per_minute=20,  # < min
        )


@pytest.mark.asyncio
async def test_adaptive_start_controls_initial_bucket_size() -> None:
    clock = _FakeClock()
    limiter = HostRateLimiter(
        max_requests_per_minute=600,
        min_requests_per_minute=30,
        start_requests_per_minute=60,
        monotonic=clock,
    )

    assert limiter.current_requests_per_minute == 60.0
    assert limiter.adaptive is True


@pytest.mark.asyncio
async def test_observe_success_climbs_rate_after_interval() -> None:
    clock = _FakeClock()
    limiter = HostRateLimiter(
        max_requests_per_minute=600,
        min_requests_per_minute=30,
        start_requests_per_minute=60,
        increase_interval_seconds=60.0,
        monotonic=clock,
    )

    # Immediate success — below threshold, no climb.
    limiter.observe(status=200)
    assert limiter.current_requests_per_minute == 60.0

    # Advance past the interval and observe again.
    clock.advance(61.0)
    limiter.observe(status=200)
    assert limiter.current_requests_per_minute == 61.0

    # Pile up enough clean traffic to climb further.
    for _ in range(10):
        clock.advance(61.0)
        limiter.observe(status=200)
    assert limiter.current_requests_per_minute == 71.0


@pytest.mark.asyncio
async def test_observe_ceils_at_max() -> None:
    clock = _FakeClock()
    limiter = HostRateLimiter(
        max_requests_per_minute=65,
        min_requests_per_minute=30,
        start_requests_per_minute=60,
        increase_interval_seconds=60.0,
        monotonic=clock,
    )
    for _ in range(20):
        clock.advance(61.0)
        limiter.observe(status=200)
    assert limiter.current_requests_per_minute == 65.0


@pytest.mark.asyncio
async def test_observe_429_halves_rate_floored_at_min() -> None:
    clock = _FakeClock()
    limiter = HostRateLimiter(
        max_requests_per_minute=600,
        min_requests_per_minute=40,
        start_requests_per_minute=200,
        monotonic=clock,
    )

    limiter.observe(status=429)
    assert limiter.current_requests_per_minute == 100.0

    limiter.observe(status=429)
    assert limiter.current_requests_per_minute == 50.0

    # One more halving would go under 40; should clamp to min.
    limiter.observe(status=429)
    assert limiter.current_requests_per_minute == 40.0


@pytest.mark.asyncio
async def test_observe_503_and_exception_also_halve() -> None:
    clock = _FakeClock()
    limiter = HostRateLimiter(
        max_requests_per_minute=600,
        min_requests_per_minute=30,
        start_requests_per_minute=120,
        monotonic=clock,
    )

    limiter.observe(status=503)
    assert limiter.current_requests_per_minute == 60.0

    limiter.observe(exception=RuntimeError("connection reset"))
    assert limiter.current_requests_per_minute == 30.0


@pytest.mark.asyncio
async def test_retry_after_sets_pause_deadline(monkeypatch: pytest.MonkeyPatch) -> None:
    clock = _FakeClock()
    sleeps: list[float] = []

    async def _record_sleep(seconds: float) -> None:
        sleeps.append(seconds)
        clock.advance(seconds)

    limiter = HostRateLimiter(
        max_requests_per_minute=600,
        min_requests_per_minute=60,
        start_requests_per_minute=120,
        monotonic=clock,
    )
    limiter.observe(status=429, retry_after_seconds=5.0)

    import platform_control.services.politeness as politeness

    original_sleep = asyncio.sleep
    politeness.asyncio.sleep = _record_sleep  # type: ignore[assignment]
    try:
        permit = await limiter.acquire("example.com")
    finally:
        politeness.asyncio.sleep = original_sleep  # type: ignore[assignment]
    permit.release()

    # First sleep should be the full 5s Retry-After pause.
    assert sleeps
    assert sleeps[0] == pytest.approx(5.0, rel=0.05)


@pytest.mark.asyncio
async def test_static_behaviour_preserved_when_corridor_not_set() -> None:
    clock = _FakeClock()
    limiter = HostRateLimiter(
        max_requests_per_minute=60,
        monotonic=clock,
    )

    # Without min/start, current == max and adaptive is False.
    assert limiter.current_requests_per_minute == 60.0
    assert limiter.adaptive is False

    # Success still a no-op (already at max).
    clock.advance(120.0)
    limiter.observe(status=200)
    assert limiter.current_requests_per_minute == 60.0


@pytest.mark.asyncio
async def test_4xx_other_than_429_does_not_change_rate() -> None:
    clock = _FakeClock()
    limiter = HostRateLimiter(
        max_requests_per_minute=600,
        min_requests_per_minute=30,
        start_requests_per_minute=120,
        monotonic=clock,
    )

    for status in (400, 401, 403, 404):
        limiter.observe(status=status)
        assert limiter.current_requests_per_minute == 120.0
