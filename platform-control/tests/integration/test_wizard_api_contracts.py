from __future__ import annotations

from datetime import UTC, datetime

import httpx
import pytest

from platform_control.database import get_session
from platform_control.main import create_app
from platform_control.routers.wizard import get_orchestrator
from platform_control.services.orchestrator import InMemoryOrchestrator


@pytest.fixture
def _app(session_maker):
    app = create_app()

    async def override_session():
        async with session_maker() as session:
            yield session

    app.dependency_overrides[get_session] = override_session
    app.dependency_overrides[get_orchestrator] = lambda: InMemoryOrchestrator()
    yield app
    app.dependency_overrides.clear()


@pytest.fixture
async def client(_app):
    transport = httpx.ASGITransport(app=_app)
    async with httpx.AsyncClient(transport=transport, base_url="http://testserver") as c:
        yield c


@pytest.mark.asyncio
async def test_wizard_api_happy_path(client, session_maker) -> None:
    project = await client.post("/v1/wizard/projects", json={"name": "Wizard IT"})
    assert project.status_code == 201
    project_id = project.json()["wizard_project_id"]

    scope = await client.post(
        f"/v1/wizard/projects/{project_id}/scope",
        json={"scope": {"domains": ["example.it"], "hierarchy": ["country", "court"]}},
    )
    assert scope.status_code == 200

    plan = await client.post(
        f"/v1/wizard/projects/{project_id}/discovery-plan",
        json={"discovery_plan": {"seed_urls": ["https://example.it"]}},
    )
    assert plan.status_code == 200

    pilot = await client.post(
        f"/v1/wizard/projects/{project_id}/pilot-run",
        json={"sample_limit": 10},
    )
    assert pilot.status_code == 200
    assert pilot.json()["state"] == "HumanGateApproval"
    run_id = pilot.json()["wizard_run_id"]

    approve = await client.post(
        f"/v1/wizard/runs/{run_id}/approve",
        json={"reason": "pilot quality passes"},
    )
    assert approve.status_code == 200
    assert approve.json()["state"] == "ScaledRun"

    reject_after_scale = await client.post(
        f"/v1/wizard/runs/{run_id}/reject",
        json={"reason": "too late"},
    )
    assert reject_after_scale.status_code == 409

    create_task = await client.post(
        "/v1/reviews/tasks",
        json={
            "wizard_run_id": run_id,
            "argilla_external_id": "api_argilla_1",
            "record_id": "rec_1",
            "payload": {
                "fields": {"title": "Decision 1"},
                "metadata": {"recordConfidence": 0.82},
            },
        },
    )
    assert create_task.status_code == 201
    assert create_task.json()["enqueue_outcome"] == "skipped_not_configured"
    task_id = create_task.json()["review_task_id"]

    sync_payload = {
        "tasks": [
            {
                "external_id": "api_argilla_1",
                "annotation_updated_at": datetime(2026, 4, 7, 13, 0, tzinfo=UTC).isoformat(),
                "decision": "accept",
                "reviewed_by": "reviewer_api",
                "payload": {"decision": "accept"},
            }
        ]
    }
    sync_first = await client.post("/v1/reviews/sync-from-argilla", json=sync_payload)
    assert sync_first.status_code == 200
    assert sync_first.json()["accepted"] == 1

    sync_second = await client.post("/v1/reviews/sync-from-argilla", json=sync_payload)
    assert sync_second.status_code == 200
    assert sync_second.json()["duplicates"] == 1

    fetched = await client.get(f"/v1/reviews/tasks/{task_id}")
    assert fetched.status_code == 200
    assert fetched.json()["status"] == "completed"
    assert fetched.json()["argilla_external_id"] == "api_argilla_1"
