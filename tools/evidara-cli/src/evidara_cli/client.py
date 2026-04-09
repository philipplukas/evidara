from __future__ import annotations

import json
import os
from typing import Any
from urllib.parse import urljoin

import httpx

DEFAULT_PLATFORM_CONTROL_URL = "http://localhost:8000"
DEFAULT_LEGAL_SEARCH_URL = "http://localhost:3102"
DEFAULT_PLATFORM_CONTROL_ADMIN_URL = "http://localhost:3100"
DEFAULT_LEGAL_SEARCH_FRONTEND_URL = "http://localhost:3101"


def _truthy(name: str) -> bool:
    return os.environ.get(name, "").strip().lower() in ("1", "true", "yes")


def platform_control_base_url() -> str:
    return os.environ.get("EVIDARA_PLATFORM_CONTROL_URL", DEFAULT_PLATFORM_CONTROL_URL).rstrip("/")


def platform_control_headers(*, correlation_id: str | None) -> dict[str, str]:
    headers: dict[str, str] = {"Accept": "application/json"}
    token = os.environ.get("EVIDARA_PLATFORM_CONTROL_TOKEN", "").strip()
    if token:
        headers["Authorization"] = f"Bearer {token}"
    key = os.environ.get("EVIDARA_PLATFORM_CONTROL_API_KEY", "").strip()
    if key:
        headers["X-API-Key"] = key
    if correlation_id:
        headers["X-Correlation-Id"] = correlation_id
    return headers


def legal_search_base_url() -> str:
    return os.environ.get("EVIDARA_LEGAL_SEARCH_URL", DEFAULT_LEGAL_SEARCH_URL).rstrip("/")


def platform_control_admin_base_url() -> str:
    return os.environ.get(
        "EVIDARA_PLATFORM_CONTROL_ADMIN_URL",
        DEFAULT_PLATFORM_CONTROL_ADMIN_URL,
    ).rstrip("/")


def legal_search_frontend_base_url() -> str:
    return os.environ.get(
        "EVIDARA_LEGAL_SEARCH_FRONTEND_URL",
        DEFAULT_LEGAL_SEARCH_FRONTEND_URL,
    ).rstrip("/")


def legal_search_headers(*, correlation_id: str | None) -> dict[str, str]:
    headers: dict[str, str] = {"Accept": "application/json"}
    token = os.environ.get("EVIDARA_LEGAL_SEARCH_TOKEN", "").strip()
    if token:
        headers["Authorization"] = f"Bearer {token}"
    api_key = os.environ.get("EVIDARA_LEGAL_SEARCH_API_KEY", "").strip()
    if api_key:
        headers["X-API-Key"] = api_key
    if correlation_id:
        headers["X-Correlation-Id"] = correlation_id
    return headers


def use_human_output() -> bool:
    return _truthy("EVIDARA_CLI_HUMAN")


class HttpJsonError(RuntimeError):
    def __init__(self, message: str, *, status_code: int | None, body: str) -> None:
        super().__init__(message)
        self.status_code = status_code
        self.body = body


def request_json(
    method: str,
    url: str,
    *,
    headers: dict[str, str],
    json_body: Any | None = None,
    params: dict[str, Any] | None = None,
    timeout: float = 120.0,
    client: httpx.Client | None = None,
) -> Any:
    def _call(c: httpx.Client) -> httpx.Response:
        return c.request(
            method,
            url,
            headers=headers,
            json=json_body,
            params=params,
        )

    try:
        if client is not None:
            response = _call(client)
        else:
            with httpx.Client(timeout=timeout) as c:
                response = _call(c)
    except httpx.HTTPError as exc:
        raise HttpJsonError(
            f"HTTP request failed {method} {url}",
            status_code=None,
            body=str(exc),
        ) from exc
    text = response.text
    if response.status_code >= 400:
        raise HttpJsonError(
            f"HTTP {response.status_code} {method} {url}",
            status_code=response.status_code,
            body=text,
        )
    if not text.strip():
        return None
    try:
        return json.loads(text)
    except json.JSONDecodeError as exc:
        raise HttpJsonError(
            "Response was not valid JSON",
            status_code=response.status_code,
            body=text,
        ) from exc


def request_status(
    method: str,
    url: str,
    *,
    headers: dict[str, str],
    params: dict[str, Any] | None = None,
    timeout: float = 120.0,
    client: httpx.Client | None = None,
) -> int:
    def _call(c: httpx.Client) -> httpx.Response:
        return c.request(
            method,
            url,
            headers=headers,
            params=params,
        )

    try:
        if client is not None:
            response = _call(client)
        else:
            with httpx.Client(timeout=timeout) as c:
                response = _call(c)
    except httpx.HTTPError as exc:
        raise HttpJsonError(
            f"HTTP request failed {method} {url}",
            status_code=None,
            body=str(exc),
        ) from exc
    return response.status_code


def join_url(base: str, path: str) -> str:
    return urljoin(base.rstrip("/") + "/", path.lstrip("/"))
