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
"""

from __future__ import annotations

import hmac

from fastapi import HTTPException, Security, status
from fastapi.security import APIKeyHeader

from platform_control.config import Settings, get_settings

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
