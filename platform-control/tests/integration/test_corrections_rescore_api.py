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
_OPERATOR = "op_01jqs7p1bcvz2tw5kxh9mq80fg"


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
            headers={"X-Operator-Id": _OPERATOR},
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
            headers={"X-Operator-Id": _OPERATOR},
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
