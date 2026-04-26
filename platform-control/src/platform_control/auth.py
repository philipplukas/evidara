"""API-key authentication and coarse authorization for platform-control.

When no API keys are configured, dependencies are a no-op (local development).

**Legacy single key** — only ``PLATFORM_CONTROL_API_KEY`` is set: any protected
route accepts that key (same behavior as before scoped keys existed).

**Scoped keys** — ``PLATFORM_CONTROL_OPERATOR_API_KEY`` and/or
``PLATFORM_CONTROL_SERVICE_API_KEY`` are set:

- Operator (admin / control-plane) routes require the operator key, or the
  legacy ``PLATFORM_CONTROL_API_KEY`` (full-access bootstrap), or the operator
  scoped key. A valid **service-only** key receives **403 Forbidden**.
- Service (pipeline ingest) routes accept the service key, operator key, or
  legacy full-access key.

Health endpoints stay unauthenticated (see ``main.create_app``).

**Principal resolution (#452, M11/B1)** — :func:`get_current_principal` is the
new dependency that returns a typed :class:`Principal` for the
authenticated caller, looking up the durable ``op_*`` ID via the
``operators`` table. Until B2 (#453) lands, callers still use
``Depends(require_control_plane_operator)`` purely for gating; new code
that needs the operator's identity should depend on
``get_current_principal`` instead.
"""

from __future__ import annotations

import hmac

from fastapi import Depends, HTTPException, Security, status
from fastapi.security import APIKeyHeader
from pydantic import BaseModel, ConfigDict
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from platform_control.config import Settings, get_settings
from platform_control.database import get_session
from platform_control.models.operator import Operator

_API_KEY_HEADER = APIKeyHeader(name="X-API-Key", auto_error=False)


def _timing_safe_equal(expected: str, provided: str | None) -> bool:
    if provided is None:
        return False
    return hmac.compare_digest(expected, provided)


def _auth_configured(settings: Settings) -> bool:
    return bool(settings.api_key or settings.operator_api_key or settings.service_api_key)


def _scoped_keys_configured(settings: Settings) -> bool:
    """True when operator and/or service scoped keys are in use (not legacy-only)."""
    return bool(settings.operator_api_key or settings.service_api_key)


def _matches_full_access(settings: Settings, api_key: str | None) -> bool:
    return _timing_safe_equal(settings.api_key, api_key) if settings.api_key else False


def _matches_operator(settings: Settings, api_key: str | None) -> bool:
    if _matches_full_access(settings, api_key):
        return True
    if settings.operator_api_key:
        return _timing_safe_equal(settings.operator_api_key, api_key)
    return False


def _matches_service_route(settings: Settings, api_key: str | None) -> bool:
    if _matches_operator(settings, api_key):
        return True
    if settings.service_api_key:
        return _timing_safe_equal(settings.service_api_key, api_key)
    return False


def _matches_service_only(settings: Settings, api_key: str | None) -> bool:
    """Key is valid for service routes but not for operator routes."""
    if api_key is None:
        return False
    if _matches_operator(settings, api_key):
        return False
    return bool(settings.service_api_key and _timing_safe_equal(settings.service_api_key, api_key))


async def require_api_key(
    api_key: str | None = Security(_API_KEY_HEADER),  # noqa: B008
) -> None:
    """Require a valid API key when any key is configured (legacy behavior).

    Equivalent to :func:`require_control_plane_operator` — kept for callers and
    docs that referenced the original name.
    """
    await require_control_plane_operator(api_key=api_key)


async def require_control_plane_operator(
    api_key: str | None = Security(_API_KEY_HEADER),  # noqa: B008
) -> None:
    """Operator/admin routes: full-access or operator key; reject service-only with 403."""
    settings = get_settings()
    if not _auth_configured(settings):
        return

    if not _scoped_keys_configured(settings):
        if api_key is None or not _matches_full_access(settings, api_key):
            raise _unauthorized()
        return

    if api_key is None:
        raise _unauthorized()
    if _matches_operator(settings, api_key):
        return
    if _matches_service_only(settings, api_key):
        raise HTTPException(
            status_code=status.HTTP_403_FORBIDDEN,
            detail="API key is not permitted for this control-plane operation",
        )
    raise _unauthorized()


async def require_control_plane_service(
    api_key: str | None = Security(_API_KEY_HEADER),  # noqa: B008
) -> None:
    """Pipeline / webhook / DI ingest routes: service, operator, or full-access key."""
    settings = get_settings()
    if not _auth_configured(settings):
        return

    if not _scoped_keys_configured(settings):
        if api_key is None or not _matches_full_access(settings, api_key):
            raise _unauthorized()
        return

    if api_key is None or not _matches_service_route(settings, api_key):
        raise _unauthorized()


def _unauthorized() -> HTTPException:
    return HTTPException(
        status_code=status.HTTP_401_UNAUTHORIZED,
        detail="Invalid or missing API key",
        headers={"WWW-Authenticate": "ApiKey"},
    )


# ─── Principal resolution (M11/B1, #452) ─────────────────────────────────────


class Principal(BaseModel):
    """Authenticated control-plane operator identity.

    Returned by :func:`get_current_principal` so write-action routes can
    attribute durable audit references (``operator_id``) without reading
    the legacy ``X-Operator-Id`` header. ``auth_principal`` is the
    identifier the auth layer used to resolve this operator (a constant
    string per scoped key today; an OIDC sub or IAP claim later).
    """

    operator_id: str
    auth_principal: str
    display_name: str

    model_config = ConfigDict(frozen=True)


_LOCAL_DEV_PRINCIPAL = Principal(
    # Reserved system ULID; mirrors migration 20260426_0017's seed.
    operator_id="op_00000000000000000000000001",
    auth_principal="local_dev",
    display_name="Local Dev",
)


def _resolve_auth_principal(settings: Settings, api_key: str) -> str | None:
    """Map a presented API key to the constant ``auth_principal`` string.

    Returns ``None`` when the key matches no configured slot. Multiple
    slots can match (legacy + scoped operator); we prefer the most
    specific name so audit records stay legible.
    """
    if settings.operator_api_key and _timing_safe_equal(settings.operator_api_key, api_key):
        return "scoped_operator_key"
    if settings.api_key and _timing_safe_equal(settings.api_key, api_key):
        return "legacy_full_access"
    return None


async def get_current_principal(
    api_key: str | None = Security(_API_KEY_HEADER),  # noqa: B008
    session: AsyncSession = Depends(get_session),  # noqa: B008
) -> Principal:
    """Resolve the authenticated caller to an :class:`Operator` row.

    Local-dev mode (no API keys configured) returns the static
    ``op_local_dev`` principal without a DB lookup. Configured mode
    requires the presented key to map to an enabled operator row;
    unmapped principals raise 403 (fail-closed).
    """
    settings = get_settings()
    if not _auth_configured(settings):
        return _LOCAL_DEV_PRINCIPAL

    if api_key is None:
        raise _unauthorized()
    if not _matches_operator(settings, api_key):
        if _matches_service_only(settings, api_key):
            raise HTTPException(
                status_code=status.HTTP_403_FORBIDDEN,
                detail="API key is not permitted for this control-plane operation",
            )
        raise _unauthorized()

    auth_principal = _resolve_auth_principal(settings, api_key)
    if auth_principal is None:  # pragma: no cover — defensive
        raise _unauthorized()

    stmt = select(Operator).where(
        Operator.auth_principal == auth_principal,
        Operator.disabled_at.is_(None),
    )
    operator = (await session.execute(stmt)).scalar_one_or_none()
    if operator is None:
        raise HTTPException(
            status_code=status.HTTP_403_FORBIDDEN,
            detail=f"No enabled operator mapped to auth principal {auth_principal!r}",
        )
    return Principal(
        operator_id=operator.operator_id,
        auth_principal=operator.auth_principal,
        display_name=operator.display_name,
    )
