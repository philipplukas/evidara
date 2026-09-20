"""`GET /v1/sources/{id}/versions` must not 500 over one unreadable row (#953).

The route builds its response model inside the handler, so a `ValidationError` from
the provider-discriminated `acquisition_spec` union escaped every registered
exception handler and became a bare 500. The panel then rendered that 500 as "no
version" — see `SourceHealthCard.test.ts` for the other half of the fix.

This is the HTTP-level assertion because the defect was only visible at HTTP level:
the service returns ORM rows fine, and it is response construction that raised.
"""

from __future__ import annotations

from datetime import UTC, datetime

import httpx
import pytest
from conftest import dispatchable_compliance_policy
from sqlalchemy.ext.asyncio import AsyncSession, async_sessionmaker

from platform_control.database import get_session
from platform_control.domain import ExecutionMode, SourceStatus, SourceVersionStatus
from platform_control.main import create_app
from platform_control.models.authority import Authority, Jurisdiction
from platform_control.models.source import Source
from platform_control.models.source_version import SourceVersion

#: A spec no member of the union can claim — it carries no `provider` discriminator.
#: This is byte-for-byte what `seed_demo_runs` wrote before #953.
UNREADABLE_SPEC = {"kind": "demo_fixture", "targets": []}


async def _seed(session_maker: async_sessionmaker[AsyncSession]) -> None:
    async with session_maker() as session:
        policy = dispatchable_compliance_policy()
        session.add(policy)
        session.add(
            Jurisdiction(
                jurisdiction_id="jur_ch",
                name="Switzerland",
                slug="ch",
                compliance_policy_id=policy.compliance_policy_id,
            )
        )
        session.add(
            Authority(
                authority_id="auth_test",
                jurisdiction_id="jur_ch",
                name="Test authority",
                slug="test-authority",
            )
        )
        for source_id, name in (
            ("src_broken_spec", "Source with an unreadable spec"),
            ("src_no_versions", "Source with no versions at all"),
        ):
            session.add(
                Source(
                    source_id=source_id,
                    name=name,
                    jurisdiction_id="jur_ch",
                    authority_id="auth_test",
                    source_type="website",
                    status=SourceStatus.ACTIVE,
                )
            )
        now = datetime.now(UTC)
        session.add(
            SourceVersion(
                source_version_id="sv_broken_spec",
                source_id="src_broken_spec",
                version_label="broken-spec",
                status=SourceVersionStatus.DRAFT,
                execution_mode=ExecutionMode.SHADOW,
                acquisition_spec=UNREADABLE_SPEC,
                created_at=now,
                updated_at=now,
            )
        )
        await session.commit()


def _client(session_maker: async_sessionmaker[AsyncSession]) -> httpx.AsyncClient:
    app = create_app()

    async def override_get_session():
        async with session_maker() as session:
            yield session

    app.dependency_overrides[get_session] = override_get_session
    return httpx.AsyncClient(
        transport=httpx.ASGITransport(app=app, raise_app_exceptions=False),
        base_url="http://test",
    )


@pytest.mark.asyncio
async def test_unreadable_spec_returns_the_version_with_a_stated_reason(
    session_maker: async_sessionmaker[AsyncSession],
) -> None:
    await _seed(session_maker)

    async with _client(session_maker) as client:
        response = await client.get("/v1/sources/src_broken_spec/versions")

    assert response.status_code == 200, response.text
    rows = response.json()["data"]
    assert len(rows) == 1
    row = rows[0]
    # The version is still reported in full — a spec we cannot read does not make
    # the version disappear, which is what dropping the row would have claimed.
    assert row["source_version_id"] == "sv_broken_spec"
    assert row["version_label"] == "broken-spec"
    assert row["execution_mode"] == "shadow"
    assert row["acquisition_spec"] is None
    assert row["acquisition_spec_error"]


@pytest.mark.asyncio
async def test_a_broken_spec_is_distinguishable_from_no_versions_at_all(
    session_maker: async_sessionmaker[AsyncSession],
) -> None:
    """The #953 assertion proper: absent and broken must not serialise alike.

    Before the fix these two requests produced 500 and 200-empty, which the panel
    collapsed into the same em dash. After it they produce one row carrying a reason
    versus zero rows — a difference a client can act on without inspecting a status
    code it never sees.
    """
    await _seed(session_maker)

    async with _client(session_maker) as client:
        broken = await client.get("/v1/sources/src_broken_spec/versions")
        absent = await client.get("/v1/sources/src_no_versions/versions")

    assert broken.status_code == 200, broken.text
    assert absent.status_code == 200, absent.text
    assert broken.json() != absent.json()
    assert absent.json()["data"] == []


@pytest.mark.asyncio
async def test_an_unknown_source_still_reports_404_not_an_empty_list(
    session_maker: async_sessionmaker[AsyncSession],
) -> None:
    """Tolerating a bad spec must not have widened into tolerating a bad source id."""
    await _seed(session_maker)

    async with _client(session_maker) as client:
        response = await client.get("/v1/sources/src_does_not_exist/versions")

    assert response.status_code == 404
    assert "src_does_not_exist" in response.json()["detail"]
