"""Tests for the coordinator FastAPI endpoints."""

from __future__ import annotations

import json
from contextlib import asynccontextmanager
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
