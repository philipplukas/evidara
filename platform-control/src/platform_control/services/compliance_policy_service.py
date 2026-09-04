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

from dataclasses import dataclass

from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from platform_control.errors import (
    CompliancePolicyMissingError,
    InvalidStateTransitionError,
    NotFoundError,
)
from platform_control.models.authority import Authority, Jurisdiction
from platform_control.models.compliance_policy import CompliancePolicy
from platform_control.models.source import Source
from platform_control.schemas.compliance_policy import (
    CreateCompliancePolicyRequest,
    UpdateCompliancePolicyRequest,
)
from platform_control.seed_schemas import _validate_rate_corridor
from platform_control.services.politeness import HostRateLimiter
from platform_control.services.robots import RobotsChecker, RobotsContext


class RateLimiterRegistry:
    """Process-wide cache of limiters keyed by ``compliance_policy_id``.

    When a policy declares ``min_requests_per_minute_per_host`` and
    ``start_requests_per_minute_per_host`` the limiter is constructed with an
    AIMD corridor; otherwise it operates as a static cap. The cache holds the
    same instance across runs so observed state (current rate, retry-after
    deadlines) is preserved.
    """

    def __init__(self) -> None:
        self._limiters: dict[str, HostRateLimiter] = {}

    def get_or_create(self, policy: CompliancePolicy) -> HostRateLimiter:
        existing = self._limiters.get(policy.compliance_policy_id)
        if existing is not None:
            return existing
        limiter = HostRateLimiter(
            max_requests_per_minute=policy.max_requests_per_minute_per_host,
            min_requests_per_minute=policy.min_requests_per_minute_per_host,
            start_requests_per_minute=policy.start_requests_per_minute_per_host,
            max_concurrent=policy.max_concurrent_per_host,
        )
        self._limiters[policy.compliance_policy_id] = limiter
        return limiter

    def invalidate(self, compliance_policy_id: str) -> None:
        """Drop a cached limiter so the next run rebuilds with updated policy."""
        self._limiters.pop(compliance_policy_id, None)


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
            min_requests_per_minute_per_host=request.min_requests_per_minute_per_host,
            start_requests_per_minute_per_host=request.start_requests_per_minute_per_host,
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

        # Compose the effective corridor after the patch and validate it before
        # persisting. Partial patches (e.g. only bumping `max`) still need to
        # leave the persisted row in a self-consistent state.
        effective_max = payload.get(
            "max_requests_per_minute_per_host", policy.max_requests_per_minute_per_host
        )
        effective_min = payload.get(
            "min_requests_per_minute_per_host", policy.min_requests_per_minute_per_host
        )
        effective_start = payload.get(
            "start_requests_per_minute_per_host", policy.start_requests_per_minute_per_host
        )
        try:
            _validate_rate_corridor(
                min_rpm=effective_min,
                start_rpm=effective_start,
                max_rpm=effective_max,
            )
        except ValueError as exc:
            raise InvalidStateTransitionError(str(exc)) from exc

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
    # Authority-level policy takes precedence over the jurisdiction default, so
    # one jurisdiction can carry different politeness tiers per authority — e.g.
    # under jur_ch_federal, Fedlex legislation stays on the open-data policy
    # while the federal courts (auth_bger/auth_bvger/…) bind the stricter
    # public-official cp_ch_court_decisions. Falls back to the jurisdiction
    # policy when the authority has no override.
    authority_id = getattr(source, "authority_id", None)
    if authority_id is not None:
        authority = await session.get(Authority, authority_id)
        if authority is not None and authority.compliance_policy_id is not None:
            return await session.get(CompliancePolicy, authority.compliance_policy_id)
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

    Returns ``None`` when the source's jurisdiction has no policy attached. This
    is the *reporting* resolver — ``None`` means "there is no policy", and the
    caller decides what to do about it.

    It is no longer the dispatch path's resolver, and the docstring here used to
    say something the code then contradicted: callers "must treat that as 'no
    limiter' (unconstrained) and not silently substitute a default". The second
    half held; the first half made the absence mean the most permissive thing
    available, which is a default in everything but name. The dispatch path now
    calls :func:`require_politeness_envelope`, which refuses.
    """
    policy = await _resolve_policy_for_source(session, source)
    if policy is None:
        return None
    return registry.get_or_create(policy)


def _robots_context(policy: CompliancePolicy, checker: RobotsChecker) -> RobotsContext:
    user_agent = _DEFAULT_USER_AGENT
    if policy.contact_url:
        user_agent = f"{_DEFAULT_USER_AGENT} (+{policy.contact_url})"
    return RobotsContext(
        checker=checker,
        mode=policy.robots_mode,
        user_agent=user_agent,
    )


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

    This is the *reporting* resolver, kept for ``cli plan``, which describes what
    a run would do without performing any IO. The dispatch path uses
    :func:`require_politeness_envelope` instead, which refuses rather than
    returning ``None``.
    """
    policy = await _resolve_policy_for_source(session, source)
    if policy is None:
        return None
    return _robots_context(policy, checker)


COMPLIANCE_POLICY_MISSING = "compliance_policy_missing"
"""Refusal slug written at the head of the run's ``failure_reason``.

Snake-case, matching the capture-level refusal vocabulary (``original_url_missing``
and friends), so an operator auditing ``?refused=true`` can group refusals by
cause without parsing prose.
"""


@dataclass(frozen=True, slots=True)
class PolitenessEnvelope:
    """The limiter + robots pair a dispatched run must have before it fetches."""

    policy: CompliancePolicy
    limiter: HostRateLimiter
    robots: RobotsContext


async def require_politeness_envelope(
    session: AsyncSession,
    source: Source,
    registry: RateLimiterRegistry,
    checker: RobotsChecker,
) -> PolitenessEnvelope:
    """Resolve the politeness envelope for ``source``, or refuse the dispatch.

    This is the resolver the run-launch path uses, and the difference from
    :func:`resolve_rate_limiter_for_source` is the whole point: absence is an
    error here, not a ``None`` the caller is free to read as "unconstrained".

    See :class:`~platform_control.errors.CompliancePolicyMissingError` for why
    the alternative — inheriting the parent jurisdiction's policy — is the wrong
    answer in this tree.
    """
    policy = await _resolve_policy_for_source(session, source)
    if policy is None:
        authority_id = getattr(source, "authority_id", None)
        raise CompliancePolicyMissingError(
            f"{COMPLIANCE_POLICY_MISSING}: no compliance policy resolves for source "
            f"{source.source_id!r} (jurisdiction={source.jurisdiction_id!r}, "
            f"authority={authority_id!r}). A run may not reach a live host with no "
            "rate policy, no robots mode and no attribution block. There is no parent "
            "fallback on purpose — inheriting would apply a policy nobody wrote for "
            "this host. Declare one in "
            "`seeds/reference/compliance_policies.yaml` and bind it on the "
            "jurisdiction (or on the authority, which wins)."
        )
    return PolitenessEnvelope(
        policy=policy,
        limiter=registry.get_or_create(policy),
        robots=_robots_context(policy, checker),
    )
