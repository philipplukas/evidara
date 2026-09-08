"""HTTP auth behavior: legacy single key vs operator/service scoped keys."""

from __future__ import annotations

import json
from urllib.parse import urlencode

import httpx
import pytest
from fastapi.routing import APIRoute

from platform_control.auth import (
    require_api_key,
    require_control_plane_operator,
    require_control_plane_service,
)
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


_DEV_OPEN = "PLATFORM_CONTROL_AUTH_DEV_ALLOW_UNAUTHENTICATED"


@pytest.mark.asyncio
async def test_no_keys_and_no_dev_optin_fails_closed(
    session_maker, monkeypatch: pytest.MonkeyPatch
) -> None:
    """The regression that matters: an unconfigured deployment must serve nothing.

    Before this, `_auth_configured()` returning False meant "auth disabled", so a
    deployment whose API-key Secret failed to mount served the entire control plane
    to anyone who could reach it — with no signal that it was doing so.
    """
    monkeypatch.delenv(_DEV_OPEN, raising=False)
    get_settings.cache_clear()

    app = create_app()

    async def override_get_session():
        async with session_maker() as session:
            yield session

    app.dependency_overrides[get_session] = override_get_session
    try:
        transport = httpx.ASGITransport(app=app)
        async with httpx.AsyncClient(transport=transport, base_url="http://test") as client:
            # Operator route: closed.
            assert (await client.get("/v1/sources")).status_code == 503
            # Service route: closed too.
            assert (await client.post("/v1/firecrawl/webhooks", json={})).status_code == 503
            # Health stays open so probes still work — an unconfigured pod must be
            # diagnosable, and readiness is not a control-plane capability.
            assert (await client.get("/health")).status_code == 200
    finally:
        app.dependency_overrides.clear()


@pytest.mark.asyncio
async def test_no_keys_with_dev_optin_stays_open(
    session_maker, monkeypatch: pytest.MonkeyPatch
) -> None:
    """The local-development path is preserved — but only when asked for by name."""
    monkeypatch.setenv(_DEV_OPEN, "1")
    get_settings.cache_clear()

    app = create_app()

    async def override_get_session():
        async with session_maker() as session:
            yield session

    app.dependency_overrides[get_session] = override_get_session
    try:
        transport = httpx.ASGITransport(app=app)
        async with httpx.AsyncClient(transport=transport, base_url="http://test") as client:
            assert (await client.get("/v1/sources")).status_code == 200
    finally:
        app.dependency_overrides.clear()


@pytest.mark.asyncio
async def test_dev_optin_is_ignored_once_a_key_is_configured(
    session_maker, monkeypatch: pytest.MonkeyPatch
) -> None:
    """The flag must not be a backdoor: with a key set, the key is still required."""
    monkeypatch.setenv(_OP, "operator-secret")
    monkeypatch.setenv(_DEV_OPEN, "1")
    get_settings.cache_clear()

    app = create_app()

    async def override_get_session():
        async with session_maker() as session:
            yield session

    app.dependency_overrides[get_session] = override_get_session
    try:
        transport = httpx.ASGITransport(app=app)
        async with httpx.AsyncClient(transport=transport, base_url="http://test") as client:
            assert (await client.get("/v1/sources")).status_code == 401
            authed = await client.get("/v1/sources", headers={"X-API-Key": "operator-secret"})
            assert authed.status_code == 200
    finally:
        app.dependency_overrides.clear()


# --- #852: nothing but the health surface may be mounted unauthenticated -------------

#: Paths deliberately served without a key. Everything else must carry an auth
#: dependency. Adding a path here is a security decision, not a formality.
_UNAUTHENTICATED_ALLOWLIST = frozenset(
    {
        "/health",
        "/ready",
        "/metrics",
        "/stats",
        "/openapi.json",
        "/docs",
        "/docs/oauth2-redirect",
        "/redoc",
    }
)

_AUTH_DEPENDENCIES = frozenset(
    {require_control_plane_operator, require_control_plane_service, require_api_key}
)


def _route_is_authenticated(route: APIRoute) -> bool:
    return any(dep.call in _AUTH_DEPENDENCIES for dep in route.dependant.dependencies)


def test_no_unauthenticated_routes_beyond_health() -> None:
    """No route outside the health surface may be reachable without a key (#852).

    `POST /webhooks/slack/interactions` was mounted unauthenticated and, despite a
    comment claiming otherwise, unverified: it read `workflow_id` out of the request
    body and signalled approve/reject to it. This asserts the *class* of defect is
    gone, not just the one instance — a new `app.include_router(x.router)` with no
    `dependencies=` fails here.
    """
    app = create_app()
    unauthenticated = sorted(
        f"{sorted(route.methods)[0]} {route.path}"
        for route in app.routes
        if isinstance(route, APIRoute)
        and route.path not in _UNAUTHENTICATED_ALLOWLIST
        and not _route_is_authenticated(route)
    )
    assert unauthenticated == [], (
        f"routes reachable without an API key: {unauthenticated}. Mount them with "
        "`dependencies=_operator_auth` or `_service_auth`, or justify an allowlist entry."
    )


@pytest.mark.asyncio
async def test_slack_interaction_webhook_is_gone(session_maker) -> None:
    """The unverified Slack approve/reject receiver answers 404, not 200 (#852).

    The gate's only path is `POST /v1/wizard/runs/{run_id}/approve|reject`, which is
    operator-authenticated and goes through `WizardService`. The body below is the
    exact forgery the old handler honoured: a fabricated `workflow_id`, no signature.
    """
    app = create_app()

    async def override_get_session():
        async with session_maker() as session:
            yield session

    app.dependency_overrides[get_session] = override_get_session
    try:
        transport = httpx.ASGITransport(app=app)
        async with httpx.AsyncClient(transport=transport, base_url="http://test") as client:
            forged = await client.post(
                "/webhooks/slack/interactions",
                content=urlencode(
                    {
                        "payload": json.dumps(
                            {
                                "user": {"name": "attacker"},
                                "actions": [
                                    {
                                        "action_id": "gate_approve",
                                        "value": json.dumps({"workflow_id": "wizard-run-victim"}),
                                    }
                                ],
                            }
                        )
                    }
                ),
                headers={"content-type": "application/x-www-form-urlencoded"},
            )
    finally:
        app.dependency_overrides.clear()

    assert forged.status_code == 404
