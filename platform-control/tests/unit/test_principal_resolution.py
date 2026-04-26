"""Principal resolution tests (#452, M11/B1).

Covers the new `Operator` model + `get_current_principal` dependency:
- Local-dev mode returns the static `op_local_dev` principal.
- Configured-auth mode resolves the presented key to a seeded operator
  via `auth_principal`.
- Unmapped principals raise 403 (fail-closed).

Existing `require_control_plane_operator` continues to work unchanged —
B2 (#453) wires `get_current_principal` into the corrections router.
"""

from __future__ import annotations

import os

import pytest
from fastapi import HTTPException
from sqlalchemy.ext.asyncio import AsyncSession

from platform_control.auth import Principal, get_current_principal
from platform_control.config import get_settings
from platform_control.models.operator import Operator


@pytest.mark.asyncio
async def test_local_dev_returns_static_local_dev_principal(session: AsyncSession) -> None:
    """No API keys configured → static principal, no DB lookup."""
    # The test fixture cleared all env vars, so settings are unconfigured.
    principal = await get_current_principal(api_key=None, session=session)

    assert isinstance(principal, Principal)
    assert principal.operator_id == "op_00000000000000000000000001"
    assert principal.auth_principal == "local_dev"
    assert principal.display_name == "Local Dev"


@pytest.mark.asyncio
async def test_configured_auth_resolves_principal_to_seeded_operator(
    session: AsyncSession,
) -> None:
    """Operator-key mode → DB lookup via `scoped_operator_key` principal."""
    session.add(
        Operator(
            operator_id="op_team_alice",
            auth_principal="scoped_operator_key",
            display_name="Alice",
        )
    )
    await session.commit()

    os.environ["PLATFORM_CONTROL_OPERATOR_API_KEY"] = "secret-op-key"
    get_settings.cache_clear()
    try:
        principal = await get_current_principal(api_key="secret-op-key", session=session)
        assert principal.operator_id == "op_team_alice"
        assert principal.auth_principal == "scoped_operator_key"
        assert principal.display_name == "Alice"
    finally:
        del os.environ["PLATFORM_CONTROL_OPERATOR_API_KEY"]
        get_settings.cache_clear()


@pytest.mark.asyncio
async def test_configured_auth_with_unmapped_principal_raises_403(
    session: AsyncSession,
) -> None:
    """Key valid but no operator row → fail-closed 403, never op_unknown."""
    os.environ["PLATFORM_CONTROL_OPERATOR_API_KEY"] = "secret-op-key"
    get_settings.cache_clear()
    try:
        with pytest.raises(HTTPException) as exc:
            await get_current_principal(api_key="secret-op-key", session=session)
        assert exc.value.status_code == 403
        assert "scoped_operator_key" in exc.value.detail
    finally:
        del os.environ["PLATFORM_CONTROL_OPERATOR_API_KEY"]
        get_settings.cache_clear()


@pytest.mark.asyncio
async def test_configured_auth_with_missing_key_raises_401(
    session: AsyncSession,
) -> None:
    """No key presented when auth is configured → 401 (existing behavior)."""
    os.environ["PLATFORM_CONTROL_OPERATOR_API_KEY"] = "secret-op-key"
    get_settings.cache_clear()
    try:
        with pytest.raises(HTTPException) as exc:
            await get_current_principal(api_key=None, session=session)
        assert exc.value.status_code == 401
    finally:
        del os.environ["PLATFORM_CONTROL_OPERATOR_API_KEY"]
        get_settings.cache_clear()


@pytest.mark.asyncio
async def test_configured_auth_with_service_only_key_raises_403(
    session: AsyncSession,
) -> None:
    """Service-scoped key on operator route → 403 (existing scope behavior)."""
    os.environ["PLATFORM_CONTROL_OPERATOR_API_KEY"] = "operator-key"
    os.environ["PLATFORM_CONTROL_SERVICE_API_KEY"] = "service-key"
    get_settings.cache_clear()
    try:
        with pytest.raises(HTTPException) as exc:
            await get_current_principal(api_key="service-key", session=session)
        assert exc.value.status_code == 403
        assert "control-plane" in exc.value.detail.lower()
    finally:
        del os.environ["PLATFORM_CONTROL_OPERATOR_API_KEY"]
        del os.environ["PLATFORM_CONTROL_SERVICE_API_KEY"]
        get_settings.cache_clear()


def test_principal_is_frozen() -> None:
    """Principal is immutable so callers can't tamper with audit identity."""
    p = Principal(operator_id="op_x", auth_principal="x", display_name="X")
    with pytest.raises((TypeError, ValueError)):
        p.operator_id = "op_y"  # type: ignore[misc]
