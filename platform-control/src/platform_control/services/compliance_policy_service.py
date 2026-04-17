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

from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from platform_control.errors import NotFoundError
from platform_control.models.authority import Jurisdiction
from platform_control.models.compliance_policy import CompliancePolicy
from platform_control.models.source import Source
from platform_control.schemas.compliance_policy import (
    CreateCompliancePolicyRequest,
    UpdateCompliancePolicyRequest,
)
from platform_control.services.politeness import HostRateLimiter
from platform_control.services.robots import RobotsChecker, RobotsContext


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


class CompliancePolicyService:
    """CRUD operations on :class:`CompliancePolicy` and its jurisdiction attachment.

    Kept thin on purpose — the runtime behaviour lives in ``RateLimiterRegistry``
    and the politeness helpers. This class is the operator-facing surface.
    """

    def __init__(self, session: AsyncSession) -> None:
        self.session = session

    async def list_policies(self) -> list[CompliancePolicy]:
        result = await self.session.scalars(
            select(CompliancePolicy).order_by(CompliancePolicy.created_at.desc())
        )
        return list(result)

    async def get_policy(self, compliance_policy_id: str) -> CompliancePolicy:
        policy = await self.session.get(CompliancePolicy, compliance_policy_id)
        if policy is None:
            raise NotFoundError(f"CompliancePolicy not found: {compliance_policy_id}")
        return policy

    async def create_policy(self, request: CreateCompliancePolicyRequest) -> CompliancePolicy:
        policy = CompliancePolicy(
            name=request.name,
            description=request.description,
            robots_mode=request.robots_mode,
            max_requests_per_minute_per_host=request.max_requests_per_minute_per_host,
            max_concurrent_per_host=request.max_concurrent_per_host,
            retention_days=request.retention_days,
            attribution_required=request.attribution_required,
            attribution_text=request.attribution_text,
            contact_url=str(request.contact_url) if request.contact_url else None,
        )
        self.session.add(policy)
        await self.session.commit()
        await self.session.refresh(policy)
        return policy

    async def update_policy(
        self,
        compliance_policy_id: str,
        request: UpdateCompliancePolicyRequest,
    ) -> CompliancePolicy:
        policy = await self.get_policy(compliance_policy_id)
        payload = request.model_dump(exclude_unset=True)
        if "contact_url" in payload and payload["contact_url"] is not None:
            payload["contact_url"] = str(payload["contact_url"])
        for key, value in payload.items():
            setattr(policy, key, value)
        await self.session.commit()
        await self.session.refresh(policy)
        return policy

    async def attach_to_jurisdiction(
        self,
        jurisdiction_id: str,
        compliance_policy_id: str,
    ) -> Jurisdiction:
        jurisdiction = await self.session.get(Jurisdiction, jurisdiction_id)
        if jurisdiction is None:
            raise NotFoundError(f"Jurisdiction not found: {jurisdiction_id}")
        # Confirm the policy exists before pinning the FK; otherwise the INSERT
        # fails opaquely downstream when the FK is validated.
        await self.get_policy(compliance_policy_id)
        jurisdiction.compliance_policy_id = compliance_policy_id
        await self.session.commit()
        await self.session.refresh(jurisdiction)
        return jurisdiction

    async def detach_from_jurisdiction(self, jurisdiction_id: str) -> Jurisdiction:
        jurisdiction = await self.session.get(Jurisdiction, jurisdiction_id)
        if jurisdiction is None:
            raise NotFoundError(f"Jurisdiction not found: {jurisdiction_id}")
        jurisdiction.compliance_policy_id = None
        await self.session.commit()
        await self.session.refresh(jurisdiction)
        return jurisdiction


_DEFAULT_USER_AGENT = "platform-control/1.0 (+https://evidara.ai)"


async def _resolve_policy_for_source(
    session: AsyncSession, source: Source
) -> CompliancePolicy | None:
    jurisdiction = await session.get(Jurisdiction, source.jurisdiction_id)
    if jurisdiction is None or jurisdiction.compliance_policy_id is None:
        return None
    return await session.get(CompliancePolicy, jurisdiction.compliance_policy_id)


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
    policy = await _resolve_policy_for_source(session, source)
    if policy is None:
        return None
    return registry.get_or_create(policy)


async def resolve_robots_context_for_source(
    session: AsyncSession,
    source: Source,
    checker: RobotsChecker,
) -> RobotsContext | None:
    """Return the robots enforcement envelope for ``source``'s jurisdiction.

    ``None`` when the jurisdiction has no policy — same semantics as
    :func:`resolve_rate_limiter_for_source`. The ``user_agent`` falls back to a
    service default when the policy does not declare a ``contact_url`` so a
    robots-compliant UA is always used.
    """
    policy = await _resolve_policy_for_source(session, source)
    if policy is None:
        return None
    user_agent = _DEFAULT_USER_AGENT
    if policy.contact_url:
        user_agent = f"{_DEFAULT_USER_AGENT} (+{policy.contact_url})"
    return RobotsContext(
        checker=checker,
        mode=policy.robots_mode,
        user_agent=user_agent,
    )
