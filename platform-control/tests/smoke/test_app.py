from __future__ import annotations

from dataclasses import dataclass

import httpx
import pytest

from platform_control.database import get_session
from platform_control.main import create_app
from platform_control.models.authority import Authority, Jurisdiction
from platform_control.routers.runs import get_firecrawl_provider
from platform_control.services.firecrawl_provider import ProviderStartResult


@dataclass
class StubProvider:
    async def start_run(self, source, source_version, run) -> ProviderStartResult:
        del source, source_version, run
        return ProviderStartResult(
            external_job_id="crawl_smoke_123",
            request_payload={"url": "https://example.com"},
            response_payload={"id": "crawl_smoke_123", "success": True},
        )


@pytest.mark.asyncio
async def test_create_source_approve_and_trigger_run(session_maker) -> None:
    async with session_maker() as seed_session:
        seed_session.add(Jurisdiction(jurisdiction_id="jur_ch", name="Switzerland", slug="ch"))
        seed_session.add(
            Authority(
                authority_id="auth_zh_admin",
                jurisdiction_id="jur_ch",
                name="Zurich Administrative Court",
                slug="zh-admin-court",
            )
        )
        await seed_session.commit()

    app = create_app()

    async def override_get_session():
        async with session_maker() as session:
            yield session

    app.dependency_overrides[get_session] = override_get_session
    app.dependency_overrides[get_firecrawl_provider] = lambda: StubProvider()

    transport = httpx.ASGITransport(app=app)
    async with httpx.AsyncClient(transport=transport, base_url="http://testserver") as client:
        source_response = await client.post(
            "/v1/sources",
            json={
                "name": "Zurich decisions",
                "jurisdiction_id": "jur_ch",
                "authority_id": "auth_zh_admin",
            },
        )
        assert source_response.status_code == 201
        source_id = source_response.json()["source_id"]

        version_response = await client.post(
            f"/v1/sources/{source_id}/versions",
            json={
                "version_label": "v1",
                "acquisition_spec": {
                    "seed_url": "https://example.com/decisions",
                    "mode": "crawl",
                    "limit": 5,
                },
            },
        )
        assert version_response.status_code == 201
        source_version_id = version_response.json()["source_version_id"]

        approve_response = await client.post(f"/v1/versions/{source_version_id}/approve")
        assert approve_response.status_code == 200

        run_response = await client.post(
            "/v1/runs",
            json={
                "source_id": source_id,
                "source_version_id": source_version_id,
                "mode": "production",
            },
        )
        assert run_response.status_code == 201
        assert run_response.json()["status"] == "running"

    app.dependency_overrides.clear()
