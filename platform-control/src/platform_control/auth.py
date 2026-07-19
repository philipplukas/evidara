"""API-key authentication and coarse authorization for platform-control.

**Fail-closed default.** When no API keys are configured the dependencies reject
with 503 unless ``PLATFORM_CONTROL_AUTH_DEV_ALLOW_UNAUTHENTICATED`` is explicitly
set. The keyless path is a local-development convenience that must be asked for by
name — it used to be what you got by accident from a deployment with an unmounted
secret. See :func:`_dev_open_mode`.

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
import os

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


_DEV_OPEN_ENV = "PLATFORM_CONTROL_AUTH_DEV_ALLOW_UNAUTHENTICATED"
_TRUTHY = frozenset({"1", "true", "yes", "on"})


def _dev_open_requested() -> bool:
    """Read the keyless-development opt-in straight from the environment.

    Deliberately *not* a field on :class:`Settings`. The Firecrawl webhook route
    resolves ``Depends(get_settings)`` in a way that publishes the entire ``Settings``
    model as a request-body schema in the generated contract (see
    ``contracts/api/platform-control.openapi.yaml`` under ``/v1/firecrawl/webhooks``),
    so adding a field there is a contract change. A dev-only escape hatch is not worth
    a contract revision, and this keeps the flag out of the published document.
    """
    return os.environ.get(_DEV_OPEN_ENV, "").strip().lower() in _TRUTHY


def _dev_open_mode(settings: Settings) -> bool:
    """True when the keyless local-development path is *explicitly* opted into.

    Fail-closed default. Historically ``_auth_configured`` returning False meant
    "authentication disabled", so a deployment that forgot to mount
    ``PLATFORM_CONTROL_OPERATOR_API_KEY`` served the entire control plane — sources,
    runs, approvals, reference data — unauthenticated to anyone who could reach it.
    That is a fail-open default on the most privileged surface we have.

    Now the open path must be asked for by name via
    ``PLATFORM_CONTROL_AUTH_DEV_ALLOW_UNAUTHENTICATED=1``. Local compose and the test
    suite set it deliberately; nothing deployed does, so a missing key produces 503 on
    every protected route instead of silence.
    """
    return not _auth_configured(settings) and _dev_open_requested()


def _auth_misconfigured() -> HTTPException:
    return HTTPException(
        status_code=status.HTTP_503_SERVICE_UNAVAILABLE,
        detail=(
            "Authentication is not configured. Set PLATFORM_CONTROL_OPERATOR_API_KEY "
            "(and/or PLATFORM_CONTROL_SERVICE_API_KEY), or opt into the keyless "
            "local-development path with PLATFORM_CONTROL_AUTH_DEV_ALLOW_UNAUTHENTICATED=1."
        ),
    )


def check_auth_configuration(settings: Settings) -> str | None:
    """Return a fatal-misconfiguration message, or ``None`` when the config is sound.

    Called at app startup so the failure is visible in logs at boot rather than only
    as a 503 on the first request. Kept separate from ``create_app`` raising so that
    build-time importers (the contract generator, ADR-0034) can still construct the app.
    """
    if _auth_configured(settings):
        return None
    if _dev_open_requested():
        return None
    return (
        "platform-control has NO API key configured and "
        "PLATFORM_CONTROL_AUTH_DEV_ALLOW_UNAUTHENTICATED is not set: every protected "
        "route will reject with 503. Mount PLATFORM_CONTROL_OPERATOR_API_KEY."
    )


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
        if _dev_open_mode(settings):
            return
        raise _auth_misconfigured()

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
        if _dev_open_mode(settings):
            return
        raise _auth_misconfigured()

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

    Local-dev mode (no API keys configured *and* the dev opt-in flag set)
    returns the static ``op_local_dev`` principal without a DB lookup;
    unconfigured-and-not-opted-in fails closed with 503. Configured mode
    requires the presented key to map to an enabled operator row;
    unmapped principals raise 403 (fail-closed).
    """
    settings = get_settings()
    if not _auth_configured(settings):
        if _dev_open_mode(settings):
            return _LOCAL_DEV_PRINCIPAL
        raise _auth_misconfigured()

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
