"""Tests for the coordinator FastAPI endpoints."""

from __future__ import annotations

import json
from contextlib import asynccontextmanager
from typing import Any
from unittest.mock import AsyncMock, MagicMock

import pytest
from fastapi import FastAPI
from fastapi.testclient import TestClient


def _make_test_app() -> tuple[FastAPI, MagicMock, MagicMock]:
    """Build a test app with a no-op lifespan that injects mocks."""
    import coordinator.app as app_module

    temporal_mock = MagicMock()
    temporal_mock.start_workflow = AsyncMock(return_value=None)
    temporal_mock.get_workflow_handle = MagicMock()

    slack_mock = MagicMock()
    slack_mock.verify_signature = MagicMock(return_value=True)
    slack_mock.update_message = AsyncMock()
    slack_mock.close = AsyncMock()

    @asynccontextmanager
    async def test_lifespan(app: FastAPI):
        app_module._temporal_client = temporal_mock
        app_module._slack_service = slack_mock
        from coordinator.gates import GateRegistry
        app_module._gate_registry = GateRegistry()
        yield

    test_app = FastAPI(title="test", lifespan=test_lifespan)
    for route in app_module.app.routes:
        test_app.routes.append(route)

    return test_app, temporal_mock, slack_mock


@asynccontextmanager
async def _parked_lifespan(app: FastAPI):
    """Lifespan for a coordinator with no Slack credentials configured."""
    import coordinator.app as app_module
    from coordinator.gates import GateRegistry

    app_module._temporal_client = MagicMock()
    app_module._slack_service = None
    app_module._gate_registry = GateRegistry()
    yield


@pytest.fixture
def client():
    test_app, _, _ = _make_test_app()
    with TestClient(test_app) as c:
        yield c


@pytest.fixture
def client_with_mocks():
    test_app, temporal_mock, slack_mock = _make_test_app()
    with TestClient(test_app) as c:
        yield c, temporal_mock, slack_mock


class TestHealth:
    def test_health(self, client):
        resp = client.get("/health")
        assert resp.status_code == 200
        assert resp.json()["status"] == "ok"


class TestLinearWebhook:
    def test_ignores_non_update(self, client):
        resp = client.post("/webhooks/linear", json={"action": "create", "data": {}})
        assert resp.status_code == 200
        assert resp.json()["ignored"] is True

    def test_ignores_non_agent_state(self, client):
        resp = client.post(
            "/webhooks/linear",
            json={
                "action": "update",
                "data": {"state": {"name": "In Progress"}, "identifier": "TAR-999"},
            },
        )
        assert resp.status_code == 200
        assert resp.json()["ignored"] is True

    def test_dispatches_agent_task(self, client_with_mocks):
        client, temporal_mock, _ = client_with_mocks
        resp = client.post(
            "/webhooks/linear",
            json={
                "action": "update",
                "data": {
                    "state": {"name": "Ready for Agent"},
                    "identifier": "TAR-999",
                    "title": "Test issue",
                    "description": "Do the thing",
                },
            },
        )
        assert resp.status_code == 200
        body = resp.json()
        assert body["dispatched"] is True
        assert body["issue_id"] == "TAR-999"
        temporal_mock.start_workflow.assert_called_once()


class TestSlackInteraction:
    def test_handles_approve(self, client_with_mocks):
        client, temporal_mock, slack_mock = client_with_mocks

        handle_mock = MagicMock()
        handle_mock.signal = AsyncMock()
        temporal_mock.get_workflow_handle = MagicMock(return_value=handle_mock)

        payload = json.dumps({
            "actions": [{
                "action_id": "gate_approve",
                "value": json.dumps({
                    "workflow_id": "wf_123",
                    "run_id": "TAR-100",
                    "gate": "merge_to_main",
                }),
            }],
            "user": {"name": "philipp"},
            "channel": {"id": "C123"},
            "message": {"ts": "1234567890.123"},
        })

        resp = client.post(
            "/webhooks/slack",
            content=f"payload={payload}",
            headers={
                "content-type": "application/x-www-form-urlencoded",
                "x-slack-request-timestamp": "1234567890",
                "x-slack-signature": "v0=fake",
            },
        )
        assert resp.status_code == 200
        assert resp.json()["decision"] == "approved"

    def test_refuses_when_slack_is_parked(self):
        """With no Slack credentials the webhook refuses, rather than falling
        through to act on an unverified payload.

        Guard: `if _slack_service is None: raise 503` in app.slack_interaction.
        Delete it and this test goes red — the handler proceeds to dispatch the
        decision on a request nobody authenticated.
        """
        import coordinator.app as app_module

        test_app = FastAPI(title="test", lifespan=_parked_lifespan)
        for route in app_module.app.routes:
            test_app.routes.append(route)

        payload = json.dumps({
            "actions": [{
                "action_id": "gate_approve",
                "value": json.dumps({
                    "workflow_id": "wf_123",
                    "run_id": "TAR-100",
                    "gate": "merge_to_main",
                }),
            }],
            "user": {"name": "philipp"},
            "channel": {"id": "C123"},
            "message": {"ts": "1234567890.123"},
        })

        with TestClient(test_app) as c:
            resp = c.post(
                "/webhooks/slack",
                content=f"payload={payload}",
                headers={"content-type": "application/x-www-form-urlencoded"},
            )

        assert resp.status_code == 503
        assert "not enabled" in resp.json()["detail"]


class TestSlackSignatureVerification:
    """`verify_signature` must never accept a request on an unconfigured secret.

    HMAC-SHA256 keyed on the empty string is publicly computable, so without the
    empty-secret refusal any caller can mint a signature that verifies.
    """

    def _service(self, secret: str) -> Any:
        from coordinator.slack_service import SlackService

        return SlackService(bot_token="xoxb-unused", signing_secret=secret)

    def test_refuses_empty_signing_secret(self):
        import hashlib
        import hmac
        import time

        service = self._service("")
        timestamp = str(int(time.time()))
        body = b"payload=%7B%7D"
        # What an attacker computes, knowing only that the secret is empty.
        forged = "v0=" + hmac.new(
            b"", f"v0:{timestamp}:{body.decode()}".encode(), hashlib.sha256
        ).hexdigest()

        assert service.verify_signature(
            body=body, timestamp=timestamp, signature=forged
        ) is False

    def test_accepts_a_real_signature(self):
        import hashlib
        import hmac
        import time

        service = self._service("s3cret")
        timestamp = str(int(time.time()))
        body = b"payload=%7B%7D"
        signature = "v0=" + hmac.new(
            b"s3cret", f"v0:{timestamp}:{body.decode()}".encode(), hashlib.sha256
        ).hexdigest()

        assert service.verify_signature(
            body=body, timestamp=timestamp, signature=signature
        ) is True

    def test_refuses_a_non_numeric_timestamp(self):
        service = self._service("s3cret")
        assert service.verify_signature(
            body=b"", timestamp="not-a-number", signature="v0=whatever"
        ) is False
