"""API-key authentication dependency.

When ``PLATFORM_CONTROL_API_KEY`` is set, all endpoints that declare
``Depends(require_api_key)`` will reject requests lacking a valid
``X-API-Key`` header with 401 Unauthorized.

When the environment variable is **not** set the dependency is a no-op,
keeping local development friction-free.
"""

from __future__ import annotations

import hmac

from fastapi import HTTPException, Security, status
from fastapi.security import APIKeyHeader

from platform_control.config import get_settings

_API_KEY_HEADER = APIKeyHeader(name="X-API-Key", auto_error=False)


async def require_api_key(
    api_key: str | None = Security(_API_KEY_HEADER),  # noqa: B008
) -> None:
    """Raise 401 if an API key is configured but the request doesn't match."""
    settings = get_settings()
    if settings.api_key is None:
        # Auth disabled — allow all requests (dev mode)
        return

    if api_key is None or not hmac.compare_digest(api_key, settings.api_key):
        raise HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED,
            detail="Invalid or missing API key",
            headers={"WWW-Authenticate": "ApiKey"},
        )
