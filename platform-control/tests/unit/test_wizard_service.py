from __future__ import annotations

import asyncio
from datetime import UTC, datetime

import httpx
import pytest
from sqlalchemy.ext.asyncio import AsyncSession, async_sessionmaker
from temporalio.testing import WorkflowEnvironment
from temporalio.worker import Worker

from platform_control.config import get_settings
from platform_control.domain import ReviewTaskStatus, WizardRunState
from platform_control.errors import ConflictError, InvalidStateTransitionError
from platform_control.models.review_task import ReviewTask
from platform_control.schemas.wizard import (
    ArgillaReviewSyncItem,
    ArgillaReviewSyncRequest,
    CreateReviewTaskRequest,
    CreateWizardProjectRequest,
)
from platform_control.services.argilla_enqueue_service import ArgillaEnqueueService
from platform_control.services.orchestrator import InMemoryOrchestrator, TemporalOrchestrator
from platform_control.services.wizard_service import WizardService
from platform_control.temporal.activities import (
    ReviewDrainActivities,
    ScopeShardActivities,
    WizardStateActivities,
)
from platform_control.temporal.workflows import (
    ReviewDrainWorkflow,
    ScopeShardWorkflow,
    WizardRunWorkflow,
)


def _make_test_activities(
    session_maker: async_sessionmaker[AsyncSession],
) -> tuple[WizardStateActivities, ScopeShardActivities, ReviewDrainActivities]:
    """Construct activity instances wired to the test DB session factory."""
    return (
        WizardStateActivities(session_factory=session_maker),
        ScopeShardActivities(session_factory=session_maker),
        ReviewDrainActivities(session_factory=session_maker),
    )


@pytest.mark.asyncio
async def test_wizard_state_guards_and_transitions(session) -> None:
    service = WizardService(session, InMemoryOrchestrator())
    project = await service.create_project(CreateWizardProjectRequest(name="Wizard CH"))

    with pytest.raises(InvalidStateTransitionError):
        await service.start_pilot_run(project.wizard_project_id)

    await service.update_scope(
        project.wizard_project_id,
        {"hierarchy": ["country", "jurisdiction"], "domains": ["example.com"]},
    )
    await service.update_discovery_plan(
        project.wizard_project_id,
        {"seed_urls": ["https://example.com"], "max_depth": 2},
    )

    run = await service.start_pilot_run(project.wizard_project_id, sample_limit=20)
    assert run.state is WizardRunState.HUMAN_GATE_APPROVAL

    run = await service.approve_run(run.wizard_run_id, reason="pilot quality ok")
    assert run.state is WizardRunState.SCALED_RUN


@pytest.mark.asyncio
@pytest.mark.requires_network
async def test_temporal_orchestrator_starts_workflow_and_signals(
    session_maker: async_sessionmaker[AsyncSession],
) -> None:
    state_acts, shard_acts, drain_acts = _make_test_activities(session_maker)
    async with await WorkflowEnvironment.start_time_skipping() as env:
        async with Worker(
            env.client,
            task_queue="wizard",
            workflows=[WizardRunWorkflow, ScopeShardWorkflow, ReviewDrainWorkflow],
            activities=[
                state_acts.persist_pilot_completed,
                state_acts.fetch_scope_shards,
                shard_acts.run_shard_crawl,
                shard_acts.report_shard_progress,
                drain_acts.enqueue_pending_reviews,
                drain_acts.check_review_drain_complete,
            ],
        ):
            orch = TemporalOrchestrator(
                namespace="default",
                task_queue="wizard",
                client=env.client,
            )
            async with session_maker() as session:
                service = WizardService(session, orch)
                project = await service.create_project(CreateWizardProjectRequest(name="Wizard DE"))
                await service.update_scope(project.wizard_project_id, {"domains": ["example.de"]})
                await service.update_discovery_plan(
                    project.wizard_project_id,
                    {"seed_urls": ["https://example.de"], "max_depth": 1},
                )
                run = await service.start_pilot_run(project.wizard_project_id)
                assert run.workflow_id is not None
                assert run.state is WizardRunState.PILOT_RUN

            # Allow the workflow's persist_pilot_completed activity to commit the
            # PilotRun → HumanGateApproval transition before we signal approve.
            async with session_maker() as session:
                service = WizardService(session, orch)
                for _ in range(50):
                    await asyncio.sleep(0)
                    session.expire_all()
                    current = await service.get_run(run.wizard_run_id)
                    if current.state is WizardRunState.HUMAN_GATE_APPROVAL:
                        break

                approved = await service.approve_run(run.wizard_run_id, reason="ok")
                assert approved.state is WizardRunState.SCALED_RUN

            handle = env.client.get_workflow_handle(approved.workflow_id)
            assert await handle.result() == "scaled"


@pytest.mark.asyncio
@pytest.mark.requires_network
async def test_temporal_orchestrator_starts_standalone_child_workflows(
    session_maker: async_sessionmaker[AsyncSession],
) -> None:
    state_acts, shard_acts, drain_acts = _make_test_activities(session_maker)
    async with await WorkflowEnvironment.start_time_skipping() as env:
        async with Worker(
            env.client,
            task_queue="wizard",
            workflows=[WizardRunWorkflow, ScopeShardWorkflow, ReviewDrainWorkflow],
            activities=[
                state_acts.persist_pilot_completed,
                state_acts.fetch_scope_shards,
                shard_acts.run_shard_crawl,
                shard_acts.report_shard_progress,
                drain_acts.enqueue_pending_reviews,
                drain_acts.check_review_drain_complete,
            ],
        ):
            orch = TemporalOrchestrator(
                namespace="default",
                task_queue="wizard",
                client=env.client,
            )
            scope_id = await orch.start_scope_shard_workflow(
                "wrn_childtest001",
                scope_shard_key="de/hamburg",
            )
            assert "scope_shard_api" in scope_id
            scope_resume = await orch.start_scope_shard_workflow(
                "wrn_childtest001",
                scope_shard_key="de/hamburg-resume",
                resume_token="seed:checkpoint=v1",
            )
            assert "scope_shard_api" in scope_resume
            resume_handle = env.client.get_workflow_handle(scope_resume)
            assert await resume_handle.result() == "shard_complete"
            drain_id = await orch.start_review_drain_workflow("wrn_childtest001")
            assert "review_drain_api" in drain_id

            sh = env.client.get_workflow_handle(scope_id)
            dh = env.client.get_workflow_handle(drain_id)
            assert await sh.result() == "shard_complete"
            assert await dh.result() == "drain_complete"


@pytest.mark.asyncio
async def test_create_review_task_posts_to_argilla_when_configured(
    session, monkeypatch: pytest.MonkeyPatch
) -> None:
    monkeypatch.setenv("PLATFORM_CONTROL_ARGILLA_API_BASE_URL", "http://argilla.test")
    monkeypatch.setenv("PLATFORM_CONTROL_ARGILLA_API_KEY", "secret")
    monkeypatch.setenv("PLATFORM_CONTROL_ARGILLA_DATASET_ID", "ds1")
    get_settings.cache_clear()

    posts: list[httpx.Request] = []

    def handler(request: httpx.Request) -> httpx.Response:
        posts.append(request)
        return httpx.Response(201, json={"ok": True})

    mock_client = httpx.AsyncClient(transport=httpx.MockTransport(handler))
    try:
        argilla = ArgillaEnqueueService(get_settings(), client=mock_client)
        service = WizardService(session, InMemoryOrchestrator(), argilla_enqueue=argilla)

        project = await service.create_project(CreateWizardProjectRequest(name="Wizard AR"))
        await service.update_scope(
            project.wizard_project_id,
            {"domains": ["example.ar"], "hierarchy": ["country"]},
        )
        await service.update_discovery_plan(
            project.wizard_project_id,
            {"seed_urls": ["https://example.ar"], "max_depth": 1},
        )
        run = await service._get_latest_run_for_project(project.wizard_project_id)

        created = await service.create_review_task(
            CreateReviewTaskRequest(
                wizard_run_id=run.wizard_run_id,
                argilla_external_id="argilla_ext_enqueue_1",
                record_id="rec_99",
                payload={"fields": {"title": "Law"}, "metadata": {"recordConfidence": 0.5}},
            )
        )
        assert created.enqueue_outcome == "enqueued"
        assert created.argilla_enqueued_at is not None
        assert len(posts) == 1
        assert b"records" in posts[0].content
        assert b"argilla_ext_enqueue_1" in posts[0].content

        sync = await service.sync_reviews_from_argilla(
            ArgillaReviewSyncRequest(
                tasks=[
                    ArgillaReviewSyncItem(
                        external_id="argilla_ext_enqueue_1",
                        annotation_updated_at=datetime(2026, 4, 8, 10, 0, tzinfo=UTC),
                        decision="accept",
                        reviewed_by="r1",
                        payload={"decision": "accept"},
                    )
                ]
            )
        )
        assert sync.accepted == 1
    finally:
        await mock_client.aclose()
        monkeypatch.delenv("PLATFORM_CONTROL_ARGILLA_API_BASE_URL", raising=False)
        monkeypatch.delenv("PLATFORM_CONTROL_ARGILLA_API_KEY", raising=False)
        monkeypatch.delenv("PLATFORM_CONTROL_ARGILLA_DATASET_ID", raising=False)
        get_settings.cache_clear()


@pytest.mark.asyncio
async def test_create_review_task_duplicate_external_id_conflict(session) -> None:
    service = WizardService(session, InMemoryOrchestrator(), argilla_enqueue=None)
    project = await service.create_project(CreateWizardProjectRequest(name="Wizard UK"))
    await service.update_scope(project.wizard_project_id, {"domains": ["x"]})
    await service.update_discovery_plan(project.wizard_project_id, {"seed_urls": ["https://x"]})
    run = await service._get_latest_run_for_project(project.wizard_project_id)
    req = CreateReviewTaskRequest(
        wizard_run_id=run.wizard_run_id,
        argilla_external_id="dup_ext",
        payload={"fields": {}},
    )
    await service.create_review_task(req)
    with pytest.raises(ConflictError):
        await service.create_review_task(req)


@pytest.mark.asyncio
async def test_argilla_sync_is_idempotent(session) -> None:
    service = WizardService(session, InMemoryOrchestrator())
    project = await service.create_project(CreateWizardProjectRequest(name="Wizard FR"))
    run = await service._get_latest_run_for_project(project.wizard_project_id)

    session.add(
        ReviewTask(
            wizard_run_id=run.wizard_run_id,
            argilla_external_id="argilla_task_1",
            status=ReviewTaskStatus.PENDING,
            payload={"record_id": "rec_1"},
        )
    )
    await session.commit()

    payload = ArgillaReviewSyncRequest(
        tasks=[
            ArgillaReviewSyncItem(
                external_id="argilla_task_1",
                annotation_updated_at=datetime(2026, 4, 7, 12, 0, tzinfo=UTC),
                decision="accept",
                reviewed_by="reviewer_a",
                payload={"decision": "accept"},
            )
        ]
    )

    first = await service.sync_reviews_from_argilla(payload)
    second = await service.sync_reviews_from_argilla(payload)

    assert first.accepted == 1
    assert first.duplicates == 0
    assert second.accepted == 0
    assert second.duplicates == 1
