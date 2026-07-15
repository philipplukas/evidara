"""HITL correction -> apply -> rescore -> metrics smoke (#454).

This smoke intentionally crosses the API/service/Temporal/activity boundary:

- FastAPI handles authenticated correction creation.
- Postgres stores the correction audit record.
- Applying a rescore_request correction starts the Temporal workflow.
- The Temporal activity records the rescore outcome through CorrectionService.
- The metrics endpoint counts the outcome from the persisted payload.

The DI runtime itself is represented by a tiny runner injected into the
activity; this keeps the smoke deterministic while still exercising the
platform-control loop without mocking CorrectionService.
"""

from __future__ import annotations

import os
from collections.abc import AsyncIterator
from dataclasses import dataclass

import httpx
import pytest
import pytest_asyncio
from docker.errors import DockerException
from sqlalchemy.ext.asyncio import AsyncSession, async_sessionmaker, create_async_engine
from temporalio.testing import WorkflowEnvironment
from temporalio.worker import Worker
from testcontainers.core.exceptions import ContainerStartException
from testcontainers.postgres import PostgresContainer

from platform_control import models as _models  # noqa: F401
from platform_control.config import get_settings
from platform_control.database import get_session, reset_database_caches
from platform_control.main import create_app
from platform_control.models.base import Base
from platform_control.models.operator import Operator
from platform_control.routers.corrections import _default_rescore_scheduler
from platform_control.services.rescore_scheduler import (
    TemporalRescoreScheduler,
    rescore_workflow_id,
)
from platform_control.temporal.activities import (
    RescoreFromCorrectionActivities,
    TargetedRescoreRunner,
)
from platform_control.temporal.workflows import RescoreFromCorrectionWorkflow

_DOCUMENT_ID = "doc_01jq7bdptzqv3xs0c41xpw1ybg"
_OPERATOR_ID = "op_01jq7operator00000000000001"
_OPERATOR_KEY = "hitl-smoke-operator-key"
_TASK_QUEUE = "hitl-e2e-smoke"


def _to_asyncpg_url(url: str) -> str:
    if url.startswith("postgresql+psycopg://"):
        return url.replace("postgresql+psycopg://", "postgresql+asyncpg://", 1)
    if url.startswith("postgresql://"):
        return url.replace("postgresql://", "postgresql+asyncpg://", 1)
    return url


@pytest_asyncio.fixture
async def postgres_session_maker() -> AsyncIterator[async_sessionmaker[AsyncSession]]:
    previous_env = {
        "PLATFORM_CONTROL_DATABASE_URL": os.environ.get("PLATFORM_CONTROL_DATABASE_URL"),
        "PLATFORM_CONTROL_OPERATOR_API_KEY": os.environ.get("PLATFORM_CONTROL_OPERATOR_API_KEY"),
        "PLATFORM_CONTROL_API_KEY": os.environ.get("PLATFORM_CONTROL_API_KEY"),
        "PLATFORM_CONTROL_SERVICE_API_KEY": os.environ.get("PLATFORM_CONTROL_SERVICE_API_KEY"),
    }

    try:
        with PostgresContainer("postgres:16-alpine", driver="psycopg") as postgres:
            database_url = _to_asyncpg_url(postgres.get_connection_url())
            os.environ["PLATFORM_CONTROL_DATABASE_URL"] = database_url
            os.environ["PLATFORM_CONTROL_OPERATOR_API_KEY"] = _OPERATOR_KEY
            os.environ.pop("PLATFORM_CONTROL_API_KEY", None)
            os.environ.pop("PLATFORM_CONTROL_SERVICE_API_KEY", None)
            get_settings.cache_clear()
            reset_database_caches()

            engine = create_async_engine(database_url)
            async with engine.begin() as connection:
                await connection.run_sync(Base.metadata.create_all)

            yield async_sessionmaker(engine, expire_on_commit=False)

            await engine.dispose()
    except (ContainerStartException, DockerException, OSError) as exc:
        pytest.skip(f"Docker-backed Postgres is unavailable: {exc}")
    finally:
        for key, value in previous_env.items():
            if value is None:
                os.environ.pop(key, None)
            else:
                os.environ[key] = value
        get_settings.cache_clear()
        reset_database_caches()


@dataclass(slots=True)
class ChangedRescoreRunner(TargetedRescoreRunner):
    async def run_targeted_rescore(
        self,
        *,
        target_entity_type: str,
        target_entity_id: str,
        correction_id: str,
    ) -> tuple[str, str | None]:
        assert target_entity_type == "document"
        assert target_entity_id == _DOCUMENT_ID
        assert correction_id.startswith("cor_")
        return ("changed", "run_01jq7rescore000000000001")


async def _seed_operator(session_maker: async_sessionmaker[AsyncSession]) -> None:
    async with session_maker() as session:
        session.add(
            Operator(
                operator_id=_OPERATOR_ID,
                auth_principal="scoped_operator_key",
                display_name="HITL Smoke Operator",
            )
        )
        await session.commit()


@pytest.mark.asyncio
@pytest.mark.temporal
async def test_correction_apply_rescore_outcome_and_metrics_loop(
    postgres_session_maker: async_sessionmaker[AsyncSession],
    temporal_env: WorkflowEnvironment,
) -> None:
    await _seed_operator(postgres_session_maker)

    app = create_app()

    async def override_get_session():
        async with postgres_session_maker() as session:
            yield session

    app.dependency_overrides[get_session] = override_get_session

    env = temporal_env
    scheduler = TemporalRescoreScheduler(
        namespace="default",
        task_queue=_TASK_QUEUE,
        client=env.client,
    )
    app.dependency_overrides[_default_rescore_scheduler] = lambda: scheduler
    activities = RescoreFromCorrectionActivities(
        postgres_session_maker,
        rescore_runner_factory=ChangedRescoreRunner,
    )

    async with Worker(
        env.client,
        task_queue=_TASK_QUEUE,
        workflows=[RescoreFromCorrectionWorkflow],
        activities=[activities.run_targeted_rescore],
    ):
        transport = httpx.ASGITransport(app=app)
        async with httpx.AsyncClient(
            transport=transport,
            base_url="http://testserver",
            headers={"X-API-Key": _OPERATOR_KEY},
        ) as client:
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
            created = create.json()
            correction_id = created["correction_id"]
            assert created["operator_id"] == _OPERATOR_ID

            applied = await client.patch(
                f"/v1/corrections/{correction_id}",
                json={"status": "applied", "rationale": "Smoke approved."},
            )
            assert applied.status_code == 200, applied.text
            applied_body = applied.json()
            assert applied_body["status"] == "applied"
            assert applied_body["payload"]["triggered_workflow_id"] == rescore_workflow_id(
                correction_id
            )

            handle = env.client.get_workflow_handle(rescore_workflow_id(correction_id))
            workflow_result = await handle.result()
            assert workflow_result["outcome"] == "changed"
            assert workflow_result["resulting_run_id"] == "run_01jq7rescore000000000001"

            fetched = await client.get(f"/v1/corrections/{correction_id}")
            assert fetched.status_code == 200
            payload = fetched.json()["payload"]
            assert payload["rescore_outcome"] == "changed"
            assert payload["resulting_run_id"] == "run_01jq7rescore000000000001"
            assert payload["completed_at"] is not None

            metrics = await client.get("/v1/corrections/metrics")
            assert metrics.status_code == 200
            outcomes = metrics.json()["rescore_outcomes"]
            assert outcomes["applied_total"] == 1
            assert outcomes["changed"] == 1
            assert outcomes["unchanged"] == 0
            assert outcomes["failed"] == 0
