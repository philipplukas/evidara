from __future__ import annotations

import httpx
import pytest

from platform_control.database import get_session
from platform_control.main import create_app
from platform_control.models.authority import Jurisdiction


@pytest.mark.asyncio
async def test_compliance_policy_crud_and_jurisdiction_attachment(session_maker) -> None:
    async with session_maker() as seed_session:
        seed_session.add(Jurisdiction(jurisdiction_id="jur_ch", name="Switzerland", slug="ch"))
        await seed_session.commit()

    app = create_app()

    async def override_get_session():
        async with session_maker() as session:
            yield session

    app.dependency_overrides[get_session] = override_get_session

    transport = httpx.ASGITransport(app=app)
    async with httpx.AsyncClient(transport=transport, base_url="http://testserver") as client:
        # --- Create ---
        create_response = await client.post(
            "/v1/compliance-policies",
            json={
                "name": "ch-default",
                "description": "Swiss public-sector default.",
                "max_requests_per_minute_per_host": 30,
                "max_concurrent_per_host": 1,
                "contact_url": "https://evidara.ai/contact",
            },
        )
        assert create_response.status_code == 201, create_response.text
        created = create_response.json()
        policy_id = created["compliance_policy_id"]
        assert created["robots_mode"] == "strict"
        assert created["max_requests_per_minute_per_host"] == 30
        assert created["attribution_required"] is False

        # --- List ---
        list_response = await client.get("/v1/compliance-policies")
        assert list_response.status_code == 200
        listing = list_response.json()["data"]
        assert any(item["compliance_policy_id"] == policy_id for item in listing)

        # --- Get ---
        get_response = await client.get(f"/v1/compliance-policies/{policy_id}")
        assert get_response.status_code == 200
        assert get_response.json()["name"] == "ch-default"

        # --- Update ---
        patch_response = await client.patch(
            f"/v1/compliance-policies/{policy_id}",
            json={"max_requests_per_minute_per_host": 90, "attribution_required": True},
        )
        assert patch_response.status_code == 200
        patched = patch_response.json()
        assert patched["max_requests_per_minute_per_host"] == 90
        assert patched["attribution_required"] is True
        # Unchanged fields remain intact.
        assert patched["max_concurrent_per_host"] == 1

        # --- Attach to jurisdiction ---
        attach_response = await client.post(
            "/v1/jurisdictions/jur_ch/compliance-policy",
            json={"compliance_policy_id": policy_id},
        )
        assert attach_response.status_code == 200
        assert attach_response.json() == {
            "jurisdiction_id": "jur_ch",
            "compliance_policy_id": policy_id,
        }

        # --- Detach ---
        detach_response = await client.delete("/v1/jurisdictions/jur_ch/compliance-policy")
        assert detach_response.status_code == 200
        assert detach_response.json() == {
            "jurisdiction_id": "jur_ch",
            "compliance_policy_id": None,
        }


@pytest.mark.asyncio
async def test_attach_unknown_policy_returns_404(session_maker) -> None:
    async with session_maker() as seed_session:
        seed_session.add(Jurisdiction(jurisdiction_id="jur_ch", name="Switzerland", slug="ch"))
        await seed_session.commit()

    app = create_app()

    async def override_get_session():
        async with session_maker() as session:
            yield session

    app.dependency_overrides[get_session] = override_get_session

    transport = httpx.ASGITransport(app=app)
    async with httpx.AsyncClient(transport=transport, base_url="http://testserver") as client:
        response = await client.post(
            "/v1/jurisdictions/jur_ch/compliance-policy",
            json={"compliance_policy_id": "cp_missing"},
        )
        assert response.status_code == 404


@pytest.mark.asyncio
async def test_update_policy_requires_at_least_one_field(session_maker) -> None:
    app = create_app()

    async def override_get_session():
        async with session_maker() as session:
            yield session

    app.dependency_overrides[get_session] = override_get_session

    transport = httpx.ASGITransport(app=app)
    async with httpx.AsyncClient(transport=transport, base_url="http://testserver") as client:
        create = await client.post("/v1/compliance-policies", json={"name": "ch-default"})
        policy_id = create.json()["compliance_policy_id"]

        response = await client.patch(f"/v1/compliance-policies/{policy_id}", json={})
        assert response.status_code == 422
