"""HTTP-level integration test for the rescore endpoint (#427).

Covers the happy path (202 + payload) and idempotent re-fire. The
Temporal scheduler is overridden with an in-memory recorder so the
test exercises only the FastAPI surface + service plumbing.
"""

from __future__ import annotations

import httpx
import pytest

from platform_control.database import get_session
from platform_control.main import create_app
from platform_control.routers.corrections import _default_rescore_scheduler
from platform_control.services.rescore_scheduler import (
    InMemoryRescoreScheduler,
    rescore_workflow_id,
)

_DOCUMENT_ID = "doc_01jq7bdptzqv3xs0c41xpw1ybg"


@pytest.mark.asyncio
async def test_rescore_endpoint_returns_202_and_records_workflow_handle(
    session_maker,
) -> None:
    app = create_app()

    async def override_get_session():
        async with session_maker() as session:
            yield session

    scheduler = InMemoryRescoreScheduler()

    app.dependency_overrides[get_session] = override_get_session
    app.dependency_overrides[_default_rescore_scheduler] = lambda: scheduler

    transport = httpx.ASGITransport(app=app)
    async with httpx.AsyncClient(transport=transport, base_url="http://testserver") as client:
        # Create a rescore_request correction first.
        create = await client.post(
            "/v1/corrections",
            json={
                "target_entity_type": "document",
                "target_entity_id": _DOCUMENT_ID,
                "correction_type": "rescore_request",
                "payload": {"reason_code": "low_quality_extractions"},
            },
        )
        assert create.status_code == 201, create.text
        correction_id = create.json()["correction_id"]

        # Trigger the rescore.
        triggered = await client.post(f"/v1/corrections/{correction_id}/rescore")
        assert triggered.status_code == 202, triggered.text
        body = triggered.json()
        assert body["correction_id"] == correction_id
        assert body["workflow_id"] == rescore_workflow_id(correction_id)
        assert body["already_running"] is False
        assert body["triggered_at"] is not None

        # Idempotent: re-firing returns already_running=True.
        re_triggered = await client.post(f"/v1/corrections/{correction_id}/rescore")
        assert re_triggered.status_code == 202
        assert re_triggered.json()["already_running"] is True

        # Scheduler only saw one schedule call (the second was short-circuited).
        assert len(scheduler.triggered) == 1


@pytest.mark.asyncio
async def test_apply_rescore_request_records_failed_outcome_when_schedule_fails_and_can_retry(
    session_maker,
) -> None:
    app = create_app()

    async def override_get_session():
        async with session_maker() as session:
            yield session

    failing_scheduler = InMemoryRescoreScheduler(fail_with=RuntimeError("temporal unavailable"))

    app.dependency_overrides[get_session] = override_get_session
    app.dependency_overrides[_default_rescore_scheduler] = lambda: failing_scheduler

    transport = httpx.ASGITransport(app=app)
    async with httpx.AsyncClient(transport=transport, base_url="http://testserver") as client:
        create = await client.post(
            "/v1/corrections",
            json={
                "target_entity_type": "document",
                "target_entity_id": _DOCUMENT_ID,
                "correction_type": "rescore_request",
                "payload": {"reason_code": "low_quality_extractions"},
            },
        )
        assert create.status_code == 201, create.text
        correction_id = create.json()["correction_id"]

        applied = await client.patch(
            f"/v1/corrections/{correction_id}",
            json={"status": "applied", "rationale": "Approved, but Temporal is unavailable."},
        )
        assert applied.status_code == 200, applied.text
        applied_body = applied.json()
        assert applied_body["status"] == "applied"
        assert applied_body["payload"]["rescore_outcome"] == "failed"
        assert applied_body["payload"]["rescore_failure_reason"] == "temporal unavailable"
        assert "triggered_workflow_id" not in applied_body["payload"]

        metrics = await client.get("/v1/corrections/metrics")
        assert metrics.status_code == 200
        assert metrics.json()["rescore_outcomes"]["failed"] == 1

        retry_scheduler = InMemoryRescoreScheduler()
        app.dependency_overrides[_default_rescore_scheduler] = lambda: retry_scheduler

        retried = await client.post(f"/v1/corrections/{correction_id}/rescore")
        assert retried.status_code == 202, retried.text
        assert retried.json()["workflow_id"] == rescore_workflow_id(correction_id)
        assert retried.json()["already_running"] is False

        fetched = await client.get(f"/v1/corrections/{correction_id}")
        payload = fetched.json()["payload"]
        assert payload["triggered_workflow_id"] == rescore_workflow_id(correction_id)
        assert payload["triggered_at"] is not None
        assert "rescore_outcome" not in payload
        assert "rescore_failure_reason" not in payload


@pytest.mark.asyncio
async def test_rescore_endpoint_409_when_correction_is_not_rescore_request(
    session_maker,
) -> None:
    app = create_app()

    async def override_get_session():
        async with session_maker() as session:
            yield session

    app.dependency_overrides[get_session] = override_get_session
    app.dependency_overrides[_default_rescore_scheduler] = lambda: InMemoryRescoreScheduler()

    transport = httpx.ASGITransport(app=app)
    async with httpx.AsyncClient(transport=transport, base_url="http://testserver") as client:
        # Create an annotation correction (not rescore).
        create = await client.post(
            "/v1/corrections",
            json={
                "target_entity_type": "document",
                "target_entity_id": _DOCUMENT_ID,
                "correction_type": "annotation",
                "payload": {"note": "follow up"},
            },
        )
        assert create.status_code == 201
        correction_id = create.json()["correction_id"]

        triggered = await client.post(f"/v1/corrections/{correction_id}/rescore")
        assert triggered.status_code == 409
