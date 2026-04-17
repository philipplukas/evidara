from __future__ import annotations

import pytest
from sqlalchemy import select

from platform_control.domain import RobotsMode
from platform_control.models.authority import Jurisdiction
from platform_control.models.compliance_policy import CompliancePolicy


@pytest.mark.asyncio
async def test_compliance_policy_round_trips_default_values(session) -> None:
    policy = CompliancePolicy(name="eu-default")
    session.add(policy)
    await session.commit()

    loaded = await session.scalar(
        select(CompliancePolicy).where(CompliancePolicy.name == "eu-default")
    )

    assert loaded is not None
    assert loaded.robots_mode is RobotsMode.STRICT
    assert loaded.max_requests_per_minute_per_host == 60
    assert loaded.max_concurrent_per_host == 2
    assert loaded.attribution_required is False


@pytest.mark.asyncio
async def test_jurisdiction_can_reference_compliance_policy(session) -> None:
    policy = CompliancePolicy(
        name="ch-fedlex",
        robots_mode=RobotsMode.IGNORE,
        max_requests_per_minute_per_host=30,
        max_concurrent_per_host=1,
        contact_url="https://evidara.ai/contact",
    )
    session.add(policy)
    await session.flush()

    session.add(
        Jurisdiction(
            jurisdiction_id="jur_ch",
            name="Switzerland",
            slug="ch",
            compliance_policy_id=policy.compliance_policy_id,
        )
    )
    await session.commit()

    loaded = await session.get(Jurisdiction, "jur_ch")
    assert loaded is not None
    assert loaded.compliance_policy_id == policy.compliance_policy_id
