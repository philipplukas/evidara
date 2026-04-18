"""``pc plan <source_version_id>`` — dry-run an acquisition plan.

Resolves the ``SourceVersion``, dispatches to the provider's ``plan()``
implementation, and prints a human-readable summary. No network IO by default.

``--check-robots`` adds an optional live probe: each seed URL is checked
against the target host's robots.txt under the jurisdiction's policy UA, so
operators catch "this whole source is denied" mistakes before spending a real
provider call.
"""

from __future__ import annotations

import argparse
import sys
from dataclasses import dataclass

from sqlalchemy.ext.asyncio import AsyncSession, async_sessionmaker

from platform_control.config import get_settings
from platform_control.database import get_session_maker
from platform_control.errors import NotFoundError
from platform_control.models.source import Source
from platform_control.models.source_version import SourceVersion
from platform_control.services.acquisition_provider import ProviderPlan
from platform_control.services.compliance_policy_service import (
    resolve_robots_context_for_source,
)
from platform_control.services.provider_registry import ProviderRegistry
from platform_control.services.provider_registry_factory import build_provider_registry
from platform_control.services.robots import RobotsChecker


@dataclass(slots=True)
class RobotsVerdict:
    url: str
    allowed: bool
    user_agent: str


async def resolve_plan(
    session: AsyncSession,
    registry: ProviderRegistry,
    source_version_id: str,
) -> tuple[Source, SourceVersion, ProviderPlan]:
    """Load the SourceVersion and return its provider plan.

    Pure helper so the CLI surface can be unit-tested without shell invocation.
    Raises :class:`NotFoundError` when the SourceVersion or its Source is missing.
    """
    source_version = await session.get(SourceVersion, source_version_id)
    if source_version is None:
        raise NotFoundError(f"SourceVersion not found: {source_version_id}")
    source = await session.get(Source, source_version.source_id)
    if source is None:
        raise NotFoundError(f"Source not found: {source_version.source_id}")

    provider = registry.resolve_for_spec(source_version.acquisition_spec)
    plan = provider.plan(source, source_version)
    return source, source_version, plan


async def check_seed_robots(
    session: AsyncSession,
    source: Source,
    plan: ProviderPlan,
    *,
    checker: RobotsChecker | None = None,
    fallback_user_agent: str = "platform-control/1.0 (+https://evidara.ai)",
) -> list[RobotsVerdict]:
    """Probe robots.txt for each seed URL in ``plan`` and return verdicts.

    Uses the jurisdiction's ``RobotsContext`` user-agent when the source has a
    policy with ``contact_url``; otherwise falls back to the service default.
    Callers can inject a pre-seeded ``RobotsChecker`` (useful for tests); the
    default is a fresh instance with the standard TTL.
    """
    if not plan.seed_urls:
        return []
    effective_checker = checker or RobotsChecker()
    robots_context = await resolve_robots_context_for_source(session, source, effective_checker)
    user_agent = robots_context.user_agent if robots_context else fallback_user_agent
    verdicts: list[RobotsVerdict] = []
    for url in plan.seed_urls:
        allowed = await effective_checker.is_allowed(url, user_agent)
        verdicts.append(RobotsVerdict(url=url, allowed=allowed, user_agent=user_agent))
    return verdicts


def format_plan(source: Source, source_version: SourceVersion, plan: ProviderPlan) -> str:
    lines: list[str] = []
    lines.append(f"source_id            {source.source_id}")
    lines.append(f"source_name          {source.name}")
    lines.append(f"jurisdiction_id      {source.jurisdiction_id}")
    lines.append(f"authority_id         {source.authority_id}")
    lines.append(f"source_version_id    {source_version.source_version_id}")
    lines.append(f"version_label        {source_version.version_label}")
    lines.append(f"status               {source_version.status.value}")
    lines.append(f"execution_mode       {source_version.execution_mode.value}")
    lines.append("")
    lines.append(f"provider             {plan.provider}")
    if plan.mode:
        lines.append(f"mode                 {plan.mode}")
    if plan.estimated_request_count is not None:
        lines.append(f"request_budget       {plan.estimated_request_count}")
    if plan.max_discovery_depth is not None:
        lines.append(f"max_discovery_depth  {plan.max_discovery_depth}")
    if plan.request_timeout_seconds is not None:
        lines.append(f"request_timeout_s    {plan.request_timeout_seconds}")
    if plan.user_agent:
        lines.append(f"user_agent           {plan.user_agent}")
    if plan.include_paths:
        lines.append(f"include_paths        {plan.include_paths}")
    if plan.exclude_paths:
        lines.append(f"exclude_paths        {plan.exclude_paths}")
    if plan.seed_urls:
        lines.append("seed_urls:")
        for url in plan.seed_urls:
            lines.append(f"  - {url}")
    if plan.notes:
        lines.append("notes:")
        for note in plan.notes:
            lines.append(f"  - {note}")
    return "\n".join(lines)


def format_robots_verdicts(verdicts: list[RobotsVerdict]) -> str:
    if not verdicts:
        return "robots_check:\n  (no seed URLs to probe)"
    lines = ["robots_check:"]
    user_agent = verdicts[0].user_agent
    lines.append(f"  user_agent           {user_agent}")
    for verdict in verdicts:
        status = "allowed" if verdict.allowed else "DISALLOWED"
        lines.append(f"  {status:<20} {verdict.url}")
    return "\n".join(lines)


async def run_from_args(namespace: argparse.Namespace) -> int:
    session_maker: async_sessionmaker[AsyncSession] = get_session_maker()
    registry = build_provider_registry(get_settings())
    async with session_maker() as session:
        try:
            source, source_version, plan = await resolve_plan(
                session, registry, namespace.source_version_id
            )
        except NotFoundError as exc:
            print(str(exc), file=sys.stderr)
            return 2
        verdicts: list[RobotsVerdict] = []
        if getattr(namespace, "check_robots", False):
            verdicts = await check_seed_robots(session, source, plan)

    print(format_plan(source, source_version, plan))
    if verdicts:
        print("")
        print(format_robots_verdicts(verdicts))
    return 0


__all__ = [
    "RobotsVerdict",
    "check_seed_robots",
    "format_plan",
    "format_robots_verdicts",
    "resolve_plan",
    "run_from_args",
]
