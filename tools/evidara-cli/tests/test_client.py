from __future__ import annotations

from unittest.mock import MagicMock, patch

import pytest

from evidara_cli.client import (
    HttpJsonError,
    join_url,
    platform_control_headers,
    request_json,
)


def test_join_url() -> None:
    assert join_url("http://localhost:8000", "/health") == "http://localhost:8000/health"
    assert join_url("http://localhost:8000/", "v1/sources") == "http://localhost:8000/v1/sources"


def test_platform_control_headers_optional_bearer_and_api_key(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    monkeypatch.delenv("EVIDARA_PLATFORM_CONTROL_TOKEN", raising=False)
    monkeypatch.delenv("EVIDARA_PLATFORM_CONTROL_API_KEY", raising=False)
    headers = platform_control_headers(correlation_id=None)
    assert "Authorization" not in headers
    monkeypatch.setenv("EVIDARA_PLATFORM_CONTROL_TOKEN", "id_token_pc")
    headers = platform_control_headers(correlation_id=None)
    assert headers["Authorization"] == "Bearer id_token_pc"
    monkeypatch.setenv("EVIDARA_PLATFORM_CONTROL_API_KEY", "api_key_pc")
    headers = platform_control_headers(correlation_id="c1")
    assert headers["Authorization"] == "Bearer id_token_pc"
    assert headers["X-API-Key"] == "api_key_pc"
    assert headers["X-Correlation-Id"] == "c1"


@patch("evidara_cli.client.httpx.Client")
def test_request_json_raises_http_json_error_on_4xx(mock_client_cls: MagicMock) -> None:
    mock_response = MagicMock()
    mock_response.status_code = 422
    mock_response.text = '{"detail":"bad"}'

    mock_inst = MagicMock()
    mock_inst.request.return_value = mock_response
    mock_inst.__enter__.return_value = mock_inst
    mock_inst.__exit__.return_value = None
    mock_client_cls.return_value = mock_inst

    with pytest.raises(HttpJsonError) as exc_info:
        request_json("POST", "http://example.test/v1/x", headers={"Accept": "application/json"})

    assert exc_info.value.status_code == 422
    assert "bad" in exc_info.value.body
