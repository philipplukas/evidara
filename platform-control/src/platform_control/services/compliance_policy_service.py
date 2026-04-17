"""Resolve per-run rate limiters from :class:`CompliancePolicy` records.

The politeness plane is split into two pieces: :class:`HostRateLimiter` holds
the per-host state (token bucket + concurrency semaphore), while this module
maps a run's ``Source`` → ``Jurisdiction`` → ``CompliancePolicy`` to the
long-lived limiter that should govern it.

:class:`RateLimiterRegistry` caches limiters keyed by ``compliance_policy_id``
so every run targeting the same policy shares the same buckets — otherwise
back-to-back runs would each start with a full bucket and defeat the cap.
"""

from __future__ import annotations

from sqlalchemy.ext.asyncio import AsyncSession

from platform_control.models.authority import Jurisdiction
from platform_control.models.compliance_policy import CompliancePolicy
from platform_control.models.source import Source
from platform_control.services.politeness import HostRateLimiter


class RateLimiterRegistry:
    """Process-wide cache of limiters keyed by ``compliance_policy_id``."""

    def __init__(self) -> None:
        self._limiters: dict[str, HostRateLimiter] = {}

    def get_or_create(self, policy: CompliancePolicy) -> HostRateLimiter:
        existing = self._limiters.get(policy.compliance_policy_id)
        if existing is not None:
            return existing
        limiter = HostRateLimiter(
            max_requests_per_minute=policy.max_requests_per_minute_per_host,
            max_concurrent=policy.max_concurrent_per_host,
        )
        self._limiters[policy.compliance_policy_id] = limiter
        return limiter


async def resolve_rate_limiter_for_source(
    session: AsyncSession,
    source: Source,
    registry: RateLimiterRegistry,
) -> HostRateLimiter | None:
    """Return the limiter governing ``source``'s jurisdiction, if any.

    Returns ``None`` when the source's jurisdiction has no policy attached —
    callers must treat that as "no limiter" (unconstrained) and not silently
    substitute a default, because the absence is the operator's signal that the
    jurisdiction is either whitelisted (e.g. their own test domains) or that a
    policy has yet to be written.
    """
    jurisdiction = await session.get(Jurisdiction, source.jurisdiction_id)
    if jurisdiction is None or jurisdiction.compliance_policy_id is None:
        return None
    policy = await session.get(CompliancePolicy, jurisdiction.compliance_policy_id)
    if policy is None:
        return None
    return registry.get_or_create(policy)
