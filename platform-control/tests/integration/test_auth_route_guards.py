"""Route-level auth guard regression tests for scoped API keys."""

from __future__ import annotations

import httpx
import pytest

from platform_control.config import get_settings
from platform_control.database import get_session
from platform_control.main import create_app

_OP = "PLATFORM_CONTROL_OPERATOR_API_KEY"
_SVC = "PLATFORM_CONTROL_SERVICE_API_KEY"
_LEGACY = "PLATFORM_CONTROL_API_KEY"

_OPERATOR_GUARDED_PATHS = [
    "/v1/reference-data/jurisdictions",
    "/v1/reference-data/authorities",
    "/v1/sources",
    "/v1/runs",
    "/v1/schedules",
]

_SERVICE_GUARDED_PATHS = [
    "/v1/di/events/document-processing-status-updated",
    "/v1/di/events/document-processed",
    "/v1/di/events/document-withdrawn",
]


@pytest.fixture(autouse=True)
def _clean_auth_env(monkeypatch: pytest.MonkeyPatch) -> None:
    for key in (_LEGACY, _OP, _SVC):
        monkeypatch.delenv(key, raising=False)
    get_settings.cache_clear()
    yield
    get_settings.cache_clear()


@pytest.mark.asyncio
async def test_operator_guarded_routes_reject_service_key_and_allow_operator_key(
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
            for path in _OPERATOR_GUARDED_PATHS:
                unauthenticated = await client.get(path)
                assert unauthenticated.status_code == 401, path

                wrong_key = await client.get(path, headers={"X-API-Key": "wrong"})
                assert wrong_key.status_code == 401, path

                service_key = await client.get(path, headers={"X-API-Key": "service-secret"})
                assert service_key.status_code == 403, path

                operator_key = await client.get(path, headers={"X-API-Key": "operator-secret"})
                assert operator_key.status_code == 200, path
    finally:
        app.dependency_overrides.clear()


@pytest.mark.asyncio
async def test_service_guarded_routes_require_valid_scoped_key(
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
            for path in _SERVICE_GUARDED_PATHS:
                unauthenticated = await client.post(path, json={})
                assert unauthenticated.status_code == 401, path

                wrong_key = await client.post(path, json={}, headers={"X-API-Key": "wrong"})
                assert wrong_key.status_code == 401, path

                service_key = await client.post(
                    path,
                    json={},
                    headers={"X-API-Key": "service-secret"},
                )
                assert service_key.status_code == 422, path

                operator_key = await client.post(
                    path,
                    json={},
                    headers={"X-API-Key": "operator-secret"},
                )
                assert operator_key.status_code == 422, path
    finally:
        app.dependency_overrides.clear()
