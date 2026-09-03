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


# --- robots.txt pacing (Crawl-delay / Request-rate) -----------------------
#
# The limiter's corridor is what WE are willing to send. `apply_robots_delay` is
# the gap the HOST asked for, and whichever of the two is slower decides when the
# next request goes out. Nothing in this repo read either directive before this
# existed, so `robots_mode: strict` meant "obey Disallow" only.
#
# These assert on ELAPSED CLOCK TIME rather than on the sleep list, because the
# question is "was the gap actually waited for", not "how many times did the
# loop go round".


class _DrivenSleep:
    """Replaces `asyncio.sleep` and advances the fake clock instead of waiting."""

    def __init__(self, clock: _FakeClock) -> None:
        self._clock = clock
        self.calls: list[float] = []

    async def __call__(self, seconds: float) -> None:
        self.calls.append(seconds)
        self._clock.advance(seconds)


async def _acquire(limiter: HostRateLimiter, host: str) -> None:
    permit = await limiter.acquire(host)
    permit.release()


@pytest.mark.asyncio
async def test_a_declared_crawl_delay_is_actually_waited_for(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    """The load-bearing assertion: a 10 s Crawl-delay puts 10 s between requests.

    Without `apply_robots_delay` this limiter runs its policy rate — a full
    60-token bucket — and would send sixty requests back to back at a host whose
    robots.txt asked for one every ten seconds.
    """
    clock = _FakeClock()
    monkeypatch.setattr(asyncio, "sleep", _DrivenSleep(clock))
    limiter = HostRateLimiter(max_requests_per_minute=60, max_concurrent=4, monotonic=clock)
    limiter.apply_robots_delay("example.ch", 10.0)

    # The first request goes immediately: the delay is a gap BETWEEN requests.
    await _acquire(limiter, "example.ch")
    assert clock.now == 0.0

    await _acquire(limiter, "example.ch")
    assert clock.now == pytest.approx(10.0)
    await _acquire(limiter, "example.ch")
    assert clock.now == pytest.approx(20.0)


@pytest.mark.asyncio
async def test_without_the_delay_the_same_bucket_bursts(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    """The control for the test above — otherwise it proves nothing about the delay.

    Same limiter, same three requests, no declared pace: all three go out at
    once. This is exactly the traffic a `Crawl-delay: 10` host was getting.
    """
    clock = _FakeClock()
    monkeypatch.setattr(asyncio, "sleep", _DrivenSleep(clock))
    limiter = HostRateLimiter(max_requests_per_minute=60, max_concurrent=4, monotonic=clock)

    for _ in range(3):
        await _acquire(limiter, "example.ch")

    assert clock.now == 0.0


@pytest.mark.asyncio
async def test_robots_delay_only_slows_down_never_speeds_up(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    """`Crawl-delay: 1` at a 6 rpm host does not license 60 rpm.

    robots.txt is a floor on politeness, not a grant of one. This is the
    direction in which "honouring robots" could become a licence to go faster,
    so it is pinned rather than left to the reader.
    """
    clock = _FakeClock()
    monkeypatch.setattr(asyncio, "sleep", _DrivenSleep(clock))
    # 6 rpm = one token per 10 s, far slower than the declared 1 s gap.
    limiter = HostRateLimiter(max_requests_per_minute=6, max_concurrent=1, monotonic=clock)
    limiter.apply_robots_delay("example.ch", 1.0)

    # Drain the 6-token bucket; the declared 1 s gap paces these.
    for _ in range(6):
        await _acquire(limiter, "example.ch")
    assert clock.now == pytest.approx(5.0)

    # The seventh needs a token, and tokens arrive every 10 s — our pace, not
    # the site's 1 s.
    await _acquire(limiter, "example.ch")
    assert clock.now == pytest.approx(10.0)


@pytest.mark.asyncio
async def test_a_delay_read_late_binds_the_next_request_not_the_sixtieth(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    """robots.txt is fetched lazily, so the bucket is already full when the gap arrives.

    Spending those accumulated tokens first would send a burst at exactly the
    host that just asked us not to.
    """
    clock = _FakeClock()
    monkeypatch.setattr(asyncio, "sleep", _DrivenSleep(clock))
    limiter = HostRateLimiter(max_requests_per_minute=60, max_concurrent=4, monotonic=clock)

    await _acquire(limiter, "example.ch")  # unconstrained; 59 tokens left
    limiter.apply_robots_delay("example.ch", 30.0)

    await _acquire(limiter, "example.ch")
    assert clock.now == pytest.approx(30.0)


@pytest.mark.asyncio
async def test_the_delay_is_per_host_not_per_policy(monkeypatch: pytest.MonkeyPatch) -> None:
    """One policy can govern several hosts, and each publishes its own robots.txt.

    `cp_ch_lexfind` is bound to 26 cantonal jurisdictions and therefore shares
    one limiter; lexfind.ch's declared pace must not throttle a canton's own host
    or vice versa.
    """
    clock = _FakeClock()
    monkeypatch.setattr(asyncio, "sleep", _DrivenSleep(clock))
    limiter = HostRateLimiter(max_requests_per_minute=60, max_concurrent=4, monotonic=clock)
    limiter.apply_robots_delay("slow.ch", 30.0)

    for _ in range(10):
        await _acquire(limiter, "fast.ch")

    assert clock.now == 0.0


@pytest.mark.asyncio
async def test_clearing_the_delay_restores_the_policy_pace(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    """robots.txt can change and the checker's cache has a TTL, so `None` is not a no-op."""
    clock = _FakeClock()
    monkeypatch.setattr(asyncio, "sleep", _DrivenSleep(clock))
    limiter = HostRateLimiter(max_requests_per_minute=60, max_concurrent=4, monotonic=clock)
    limiter.apply_robots_delay("example.ch", 30.0)
    await _acquire(limiter, "example.ch")

    limiter.apply_robots_delay("example.ch", None)
    for _ in range(10):
        await _acquire(limiter, "example.ch")

    assert clock.now == 0.0


@pytest.mark.asyncio
async def test_a_non_positive_interval_is_not_a_pace(monkeypatch: pytest.MonkeyPatch) -> None:
    """`Crawl-delay: 0` must not install a gate that then never opens on a fake clock."""
    clock = _FakeClock()
    monkeypatch.setattr(asyncio, "sleep", _DrivenSleep(clock))
    limiter = HostRateLimiter(max_requests_per_minute=60, max_concurrent=4, monotonic=clock)
    limiter.apply_robots_delay("example.ch", 0.0)

    for _ in range(10):
        await _acquire(limiter, "example.ch")

    assert clock.now == 0.0
