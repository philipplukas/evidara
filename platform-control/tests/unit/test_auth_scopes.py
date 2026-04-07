"""HTTP auth behavior: legacy single key vs operator/service scoped keys."""

from __future__ import annotations

import httpx
import pytest

from platform_control.config import get_settings
from platform_control.database import get_session
from platform_control.main import create_app

_OP = "PLATFORM_CONTROL_OPERATOR_API_KEY"
_SVC = "PLATFORM_CONTROL_SERVICE_API_KEY"
_LEGACY = "PLATFORM_CONTROL_API_KEY"


@pytest.fixture(autouse=True)
def _clean_auth_env(monkeypatch: pytest.MonkeyPatch) -> None:
    for key in (_LEGACY, _OP, _SVC):
        monkeypatch.delenv(key, raising=False)
    get_settings.cache_clear()
    yield
    get_settings.cache_clear()


@pytest.mark.asyncio
async def test_health_unauthenticated_with_scoped_keys(
    session_maker, monkeypatch: pytest.MonkeyPatch
) -> None:
    monkeypatch.setenv(_OP, "operator-secret")
    monkeypatch.setenv(_SVC, "service-secret")
    get_settings.cache_clear()

    app = create_app()

    async def override_get_session():
        async with session_maker() as session:
            yield session

    app.dependency_overrides[get_session] = override_get_session
    try:
        transport = httpx.ASGITransport(app=app)
        async with httpx.AsyncClient(transport=transport, base_url="http://test") as client:
            health = await client.get("/health")
            assert health.status_code == 200
            ready = await client.get("/ready")
            assert ready.status_code == 200
    finally:
        app.dependency_overrides.clear()


@pytest.mark.asyncio
async def test_operator_route_401_403_200(session_maker, monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setenv(_OP, "operator-secret")
    monkeypatch.setenv(_SVC, "service-secret")
    get_settings.cache_clear()

    app = create_app()

    async def override_get_session():
        async with session_maker() as session:
            yield session

    app.dependency_overrides[get_session] = override_get_session
    try:
        transport = httpx.ASGITransport(app=app)
        async with httpx.AsyncClient(transport=transport, base_url="http://test") as client:
            r0 = await client.get("/v1/reference-data/jurisdictions")
            assert r0.status_code == 401

            r1 = await client.get(
                "/v1/reference-data/jurisdictions",
                headers={"X-API-Key": "wrong"},
            )
            assert r1.status_code == 401

            r2 = await client.get(
                "/v1/reference-data/jurisdictions",
                headers={"X-API-Key": "service-secret"},
            )
            assert r2.status_code == 403

            r3 = await client.get(
                "/v1/reference-data/jurisdictions",
                headers={"X-API-Key": "operator-secret"},
            )
            assert r3.status_code == 200
    finally:
        app.dependency_overrides.clear()


@pytest.mark.asyncio
async def test_service_route_accepts_service_and_operator_keys(
    session_maker, monkeypatch: pytest.MonkeyPatch
) -> None:
    monkeypatch.setenv(_OP, "operator-secret")
    monkeypatch.setenv(_SVC, "service-secret")
    get_settings.cache_clear()

    app = create_app()

    async def override_get_session():
        async with session_maker() as session:
            yield session

    app.dependency_overrides[get_session] = override_get_session
    try:
        transport = httpx.ASGITransport(app=app)
        async with httpx.AsyncClient(transport=transport, base_url="http://test") as client:
            r0 = await client.post("/v1/di/events/document-processing-status-updated", json={})
            assert r0.status_code == 401

            r1 = await client.post(
                "/v1/di/events/document-processing-status-updated",
                json={},
                headers={"X-API-Key": "wrong"},
            )
            assert r1.status_code == 401

            r2 = await client.post(
                "/v1/di/events/document-processing-status-updated",
                json={},
                headers={"X-API-Key": "service-secret"},
            )
            assert r2.status_code == 422

            r3 = await client.post(
                "/v1/di/events/document-processing-status-updated",
                json={},
                headers={"X-API-Key": "operator-secret"},
            )
            assert r3.status_code == 422
    finally:
        app.dependency_overrides.clear()


@pytest.mark.asyncio
async def test_legacy_single_key_same_behavior_on_both_route_groups(
    session_maker, monkeypatch: pytest.MonkeyPatch
) -> None:
    monkeypatch.setenv(_LEGACY, "legacy-only-secret")
    get_settings.cache_clear()

    app = create_app()

    async def override_get_session():
        async with session_maker() as session:
            yield session

    app.dependency_overrides[get_session] = override_get_session
    try:
        transport = httpx.ASGITransport(app=app)
        async with httpx.AsyncClient(transport=transport, base_url="http://test") as client:
            r0 = await client.get("/v1/reference-data/jurisdictions")
            assert r0.status_code == 401

            r1 = await client.get(
                "/v1/reference-data/jurisdictions",
                headers={"X-API-Key": "legacy-only-secret"},
            )
            assert r1.status_code == 200

            r2 = await client.post(
                "/v1/di/events/document-processing-status-updated",
                json={},
                headers={"X-API-Key": "legacy-only-secret"},
            )
            assert r2.status_code == 422
    finally:
        app.dependency_overrides.clear()


@pytest.mark.asyncio
async def test_full_access_key_works_when_scoped_keys_exist(
    session_maker, monkeypatch: pytest.MonkeyPatch
) -> None:
    monkeypatch.setenv(_LEGACY, "bootstrap-secret")
    monkeypatch.setenv(_OP, "operator-secret")
    monkeypatch.setenv(_SVC, "service-secret")
    get_settings.cache_clear()

    app = create_app()

    async def override_get_session():
        async with session_maker() as session:
            yield session

    app.dependency_overrides[get_session] = override_get_session
    try:
        transport = httpx.ASGITransport(app=app)
        async with httpx.AsyncClient(transport=transport, base_url="http://test") as client:
            r1 = await client.get(
                "/v1/reference-data/jurisdictions",
                headers={"X-API-Key": "bootstrap-secret"},
            )
            assert r1.status_code == 200

            r2 = await client.post(
                "/v1/di/events/document-processing-status-updated",
                json={},
                headers={"X-API-Key": "bootstrap-secret"},
            )
            assert r2.status_code == 422
    finally:
        app.dependency_overrides.clear()
