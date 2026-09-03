from __future__ import annotations

import asyncio

import pytest
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession, async_sessionmaker
from temporalio.testing import WorkflowEnvironment
from temporalio.worker import Worker

from acquisition_core.providers import ProviderPlan, ProviderResource, ProviderStartResult
from platform_control.domain import ReviewTaskStatus, RunStatus, WizardRunState
from platform_control.errors import ConflictError, InvalidStateTransitionError
from platform_control.models.authority import Authority, Jurisdiction
from platform_control.models.review_task import ReviewTask
from platform_control.models.run import Run
from platform_control.models.source import Source
from platform_control.models.source_version import SourceVersion
from platform_control.models.wizard_run import WizardRun
from platform_control.schemas.wizard import (
    CreateReviewTaskRequest,
    CreateWizardProjectRequest,
    ReviewDecisionRequest,
)
from platform_control.services.orchestrator import InMemoryOrchestrator, TemporalOrchestrator
from platform_control.services.provider_registry import ProviderRegistry
from platform_control.services.wizard_service import WizardService
from platform_control.temporal.activities import (
    ReviewDrainActivities,
    ScopeShardActivities,
    ShardDispatchInFlightError,
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
@pytest.mark.temporal
async def test_temporal_orchestrator_starts_workflow_and_signals(
    session_maker: async_sessionmaker[AsyncSession],
    temporal_env: WorkflowEnvironment,
) -> None:
    state_acts, shard_acts, drain_acts = _make_test_activities(session_maker)
    env = temporal_env
    async with Worker(
        env.client,
        task_queue="wizard",
        workflows=[WizardRunWorkflow, ScopeShardWorkflow, ReviewDrainWorkflow],
        activities=[
            state_acts.persist_pilot_completed,
            state_acts.fetch_scope_shards,
            shard_acts.run_shard_crawl,
            shard_acts.report_shard_progress,
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
@pytest.mark.temporal
async def test_temporal_orchestrator_starts_standalone_child_workflows(
    session_maker: async_sessionmaker[AsyncSession],
    temporal_env: WorkflowEnvironment,
) -> None:
    state_acts, shard_acts, drain_acts = _make_test_activities(session_maker)
    env = temporal_env
    async with Worker(
        env.client,
        task_queue="wizard",
        workflows=[WizardRunWorkflow, ScopeShardWorkflow, ReviewDrainWorkflow],
        activities=[
            state_acts.persist_pilot_completed,
            state_acts.fetch_scope_shards,
            shard_acts.run_shard_crawl,
            shard_acts.report_shard_progress,
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
async def test_create_review_task_enqueues_by_persisting_it(session) -> None:
    """Persisting the task *is* the enqueue — the queue is the table (ADR-0031).

    No outbound HTTP call, no `enqueue_outcome` side channel: the task comes back
    PENDING and the admin app picks it up from there.
    """
    service = WizardService(session, InMemoryOrchestrator())

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
            external_id="ext_enqueue_1",
            record_id="rec_99",
            payload={"fields": {"title": "Law"}, "metadata": {"recordConfidence": 0.5}},
        )
    )

    assert created.external_id == "ext_enqueue_1"
    assert created.status is ReviewTaskStatus.PENDING
    assert created.processed_at is None

    persisted = await service.get_review_task(created.review_task_id)
    assert persisted.record_id == "rec_99"


@pytest.mark.asyncio
async def test_create_review_task_duplicate_external_id_conflict(session) -> None:
    service = WizardService(session, InMemoryOrchestrator())
    project = await service.create_project(CreateWizardProjectRequest(name="Wizard UK"))
    await service.update_scope(project.wizard_project_id, {"domains": ["x"]})
    await service.update_discovery_plan(project.wizard_project_id, {"seed_urls": ["https://x"]})
    run = await service._get_latest_run_for_project(project.wizard_project_id)
    req = CreateReviewTaskRequest(
        wizard_run_id=run.wizard_run_id,
        external_id="dup_ext",
        payload={"fields": {}},
    )
    await service.create_review_task(req)
    with pytest.raises(ConflictError):
        await service.create_review_task(req)


@pytest.mark.asyncio
async def test_record_review_decision_completes_the_task(session) -> None:
    """The operator's verdict is what closes a task, now that Argilla is gone."""
    service = WizardService(session, InMemoryOrchestrator())
    project = await service.create_project(CreateWizardProjectRequest(name="Wizard FR"))
    run = await service._get_latest_run_for_project(project.wizard_project_id)

    task = ReviewTask(
        wizard_run_id=run.wizard_run_id,
        external_id="task_1",
        status=ReviewTaskStatus.PENDING,
        payload={"record_id": "rec_1"},
    )
    session.add(task)
    await session.commit()

    decided = await service.record_review_decision(
        task.review_task_id,
        # The body's `reviewed_by` is inert — the route passes the authenticated
        # principal, and that is what gets persisted.
        ReviewDecisionRequest(decision="accept", reviewed_by="a-name-the-client-made-up"),
        reviewed_by="op_reviewer_a",
    )

    assert decided.status is ReviewTaskStatus.COMPLETED
    assert decided.processed_at is not None
    assert decided.decision_payload is not None
    assert decided.decision_payload["decision"] == "accept"
    assert decided.decision_payload["reviewed_by"] == "op_reviewer_a"


@pytest.mark.asyncio
async def test_record_review_decision_conflicts_on_an_already_decided_task(session) -> None:
    """A second verdict is a 409, not a silent overwrite of the first reviewer's call."""
    service = WizardService(session, InMemoryOrchestrator())
    project = await service.create_project(CreateWizardProjectRequest(name="Wizard IT"))
    run = await service._get_latest_run_for_project(project.wizard_project_id)

    task = ReviewTask(
        wizard_run_id=run.wizard_run_id,
        external_id="task_2",
        status=ReviewTaskStatus.PENDING,
        payload={},
    )
    session.add(task)
    await session.commit()

    request = ReviewDecisionRequest(decision="accept")
    await service.record_review_decision(task.review_task_id, request, reviewed_by="op_a")

    with pytest.raises(ConflictError):
        await service.record_review_decision(task.review_task_id, request, reviewed_by="op_b")


# ---------------------------------------------------------------------------
# TAR-108: Provider dispatch from run_shard_crawl
# ---------------------------------------------------------------------------


class _FakeInlineProvider:
    """Fake provider that returns inline resources without network access."""

    provider_name = "fake_inline"
    live_ready = True

    async def start_run(self, source, source_version, run):
        return ProviderStartResult(
            provider=self.provider_name,
            external_job_id=f"fake_{run.run_id}",
            request_payload={"seed": "test"},
            response_payload={"captured": 1},
            inline_resources=[
                ProviderResource(
                    source_url="https://example.com/doc1",
                    final_url="https://example.com/doc1",
                    content_type="text/html",
                    body="<html><body>Test law</body></html>",
                    title="Test Law §1",
                    http_status=200,
                    discovery_depth=0,
                    metadata={"source_url": "https://example.com/doc1"},
                ),
            ],
        )

    def plan(self, source, source_version):
        return ProviderPlan(provider=self.provider_name)


def _build_fake_registry() -> ProviderRegistry:
    registry = ProviderRegistry()
    registry.register(_FakeInlineProvider())
    return registry


async def _seed_source_fixtures(
    session: AsyncSession,
) -> tuple[str, str]:
    """Create minimal jurisdiction → authority → source → source_version fixtures.

    Returns (source_id, source_version_id).
    """
    jur = Jurisdiction(jurisdiction_id="jur_test", name="Test", slug="test")
    session.add(jur)
    auth = Authority(
        authority_id="auth_test", jurisdiction_id="jur_test", name="Test Auth", slug="test-auth"
    )
    session.add(auth)
    await session.flush()

    source = Source(
        name="Test Source",
        jurisdiction_id="jur_test",
        authority_id="auth_test",
    )
    session.add(source)
    await session.flush()

    sv = SourceVersion(
        source_id=source.source_id,
        version_label="v1",
        acquisition_spec={"provider": "fake_inline", "seed_urls": ["https://example.com"]},
    )
    session.add(sv)
    await session.flush()
    return source.source_id, sv.source_version_id


@pytest.mark.asyncio
async def test_run_shard_crawl_dispatches_provider(session_maker) -> None:
    """TAR-108: run_shard_crawl creates a Run and dispatches the provider."""
    async with session_maker() as session:
        source_id, sv_id = await _seed_source_fixtures(session)
        await session.commit()

    # Create wizard project with source refs in discovery_plan.
    async with session_maker() as session:
        service = WizardService(session, InMemoryOrchestrator())
        project = await service.create_project(CreateWizardProjectRequest(name="TAR-108 test"))
        await service.update_scope(
            project.wizard_project_id,
            {"domains": ["example.com"]},
        )
        await service.update_discovery_plan(
            project.wizard_project_id,
            {
                "source_id": source_id,
                "source_version_id": sv_id,
            },
        )
        wizard_run = await service._get_latest_run_for_project(project.wizard_project_id)
        wizard_run_id = wizard_run.wizard_run_id
        await session.commit()

    # Run the shard crawl activity directly (no Temporal worker needed).
    shard_acts = ScopeShardActivities(
        session_factory=session_maker,
        provider_registry_factory=_build_fake_registry,
    )
    result = await shard_acts.run_shard_crawl(wizard_run_id, "default", None)

    assert result["status"] == "completed", f"Unexpected result: {result}"
    assert result["nodes_discovered"] >= 1
    assert "run_id" in result

    # Verify a Run record was persisted.
    async with session_maker() as session:
        run = await session.get(Run, result["run_id"])
        assert run is not None
        assert run.status is RunStatus.COMPLETED
        assert run.captured_resources_count >= 1


@pytest.mark.asyncio
async def test_run_shard_crawl_skips_without_source_ref(session_maker) -> None:
    """run_shard_crawl returns skipped when discovery_plan has no source refs."""
    async with session_maker() as session:
        service = WizardService(session, InMemoryOrchestrator())
        project = await service.create_project(CreateWizardProjectRequest(name="No refs"))
        await service.update_scope(
            project.wizard_project_id,
            {"domains": ["example.com"]},
        )
        await service.update_discovery_plan(
            project.wizard_project_id,
            {"seed_urls": ["https://example.com"]},
        )
        wizard_run = await service._get_latest_run_for_project(project.wizard_project_id)
        wizard_run_id = wizard_run.wizard_run_id
        await session.commit()

    shard_acts = ScopeShardActivities(
        session_factory=session_maker,
        provider_registry_factory=_build_fake_registry,
    )
    result = await shard_acts.run_shard_crawl(wizard_run_id, "default", None)
    assert result["status"] == "skipped_no_source_ref"


# ---------------------------------------------------------------------------
# #561: the shard crawl is idempotent, and progress writes do not lose updates
# ---------------------------------------------------------------------------


class _CountingProvider(_FakeInlineProvider):
    """Fake provider that records how many times it was actually dispatched."""

    def __init__(self) -> None:
        self.dispatches = 0

    async def start_run(self, source, source_version, run):
        self.dispatches += 1
        return await super().start_run(source, source_version, run)


async def _wizard_run_with_source(session_maker, name: str) -> str:
    """Seed a wizard run whose discovery plan points at a real source version."""
    async with session_maker() as session:
        source_id, sv_id = await _seed_source_fixtures(session)
        await session.commit()

    async with session_maker() as session:
        service = WizardService(session, InMemoryOrchestrator())
        project = await service.create_project(CreateWizardProjectRequest(name=name))
        await service.update_scope(project.wizard_project_id, {"domains": ["example.com"]})
        await service.update_discovery_plan(
            project.wizard_project_id,
            {"source_id": source_id, "source_version_id": sv_id},
        )
        wizard_run = await service._get_latest_run_for_project(project.wizard_project_id)
        await session.commit()
        return wizard_run.wizard_run_id


@pytest.mark.asyncio
async def test_retrying_the_shard_crawl_does_not_re_scrape_the_portal(session_maker) -> None:
    """#561: `ScopeShardWorkflow` retries `run_shard_crawl` up to five times.

    Every attempt used to create a fresh `Run` row and dispatch the provider
    again, so one transient error meant up to five duplicate rows and five full
    re-scrapes of the same shard of a government legal portal. The dedupe key on
    `runs.idempotency_key` is what stops that: the second attempt finds the first
    attempt's run and reports it instead of crawling again.
    """
    wizard_run_id = await _wizard_run_with_source(session_maker, "idempotency")
    provider = _CountingProvider()
    registry = ProviderRegistry()
    registry.register(provider)

    shard_acts = ScopeShardActivities(
        session_factory=session_maker,
        provider_registry_factory=lambda: registry,
    )

    first = await shard_acts.run_shard_crawl(wizard_run_id, "ch/zurich", None)
    second = await shard_acts.run_shard_crawl(wizard_run_id, "ch/zurich", None)
    third = await shard_acts.run_shard_crawl(wizard_run_id, "ch/zurich", None)

    assert provider.dispatches == 1, "a retried shard crawl re-scraped the portal"
    assert second["run_id"] == first["run_id"]
    assert third["run_id"] == first["run_id"]
    assert second["deduplicated"] is True

    async with session_maker() as session:
        runs = (await session.scalars(select(Run))).all()
        assert len(runs) == 1
        assert runs[0].idempotency_key == f"wizard:{wizard_run_id}:shard:ch/zurich"


class _FlakyProvider(_CountingProvider):
    """Fails its first dispatch, succeeds afterwards — a transient provider error."""

    async def start_run(self, source, source_version, run):
        self.dispatches += 1
        if self.dispatches == 1:
            raise RuntimeError("portal returned 503")
        return await _FakeInlineProvider.start_run(self, source, source_version, run)


@pytest.mark.asyncio
async def test_a_transiently_failed_shard_is_re_dispatched_on_the_same_run(
    session_maker,
) -> None:
    """Idempotency must not mean "cache the first failure forever".

    The dedupe key stops a *successful* crawl being redone. A run that ended
    FAILED is exactly what the retry policy exists for, so the next attempt
    re-arms the same row and dispatches again — one run per shard, still, but the
    shard is recoverable. Returning the stored failure instead would make a
    transient 503 permanent, which is worse than the duplicate rows #561 removed.
    """
    wizard_run_id = await _wizard_run_with_source(session_maker, "flaky")
    provider = _FlakyProvider()
    registry = ProviderRegistry()
    registry.register(provider)
    shard_acts = ScopeShardActivities(
        session_factory=session_maker,
        provider_registry_factory=lambda: registry,
    )

    first = await shard_acts.run_shard_crawl(wizard_run_id, "ch/zurich", None)
    assert first["status"] == "failed"

    second = await shard_acts.run_shard_crawl(wizard_run_id, "ch/zurich", None)

    assert provider.dispatches == 2, "the retry never reached the provider"
    assert second["status"] == "completed"
    assert second["run_id"] == first["run_id"], "the retry created a second Run row"

    async with session_maker() as session:
        runs = (await session.scalars(select(Run))).all()
        assert len(runs) == 1
        assert runs[0].status is RunStatus.COMPLETED
        assert runs[0].failure_reason is None


@pytest.mark.asyncio
async def test_a_shard_still_in_flight_raises_instead_of_reporting_zeros(
    session_maker,
) -> None:
    """An async provider's run is durable while still RUNNING — that is not an outcome.

    Returning that row's zeroed counters would be a *successful* activity return
    with no data, and `ScopeShardWorkflow` does not inspect `status`, so the shard
    would be recorded complete having captured nothing. Raising lets Temporal's
    backoff give the in-flight attempt time to land.
    """
    wizard_run_id = await _wizard_run_with_source(session_maker, "in flight")
    provider = _CountingProvider()
    registry = ProviderRegistry()
    registry.register(provider)
    shard_acts = ScopeShardActivities(
        session_factory=session_maker,
        provider_registry_factory=lambda: registry,
    )

    first = await shard_acts.run_shard_crawl(wizard_run_id, "ch/zurich", None)
    async with session_maker() as session:
        run = await session.get(Run, first["run_id"])
        assert run is not None
        run.status = RunStatus.RUNNING  # what an async/webhook provider leaves behind
        await session.commit()

    with pytest.raises(ShardDispatchInFlightError):
        await shard_acts.run_shard_crawl(wizard_run_id, "ch/zurich", None)

    assert provider.dispatches == 1, "an in-flight shard was dispatched a second time"


@pytest.mark.asyncio
async def test_starting_a_pilot_run_does_not_clobber_shard_progress(session_maker) -> None:
    """`start_pilot_run` is the third writer to `progress` and must also compare-and-set.

    It used to assign the column outright from a snapshot, which drops whatever a
    shard committed *and* leaves `progress_version` unchanged — so no CAS writer
    could detect the loss either.
    """
    async with session_maker() as session:
        source_id, sv_id = await _seed_source_fixtures(session)
        await session.commit()

    async with session_maker() as session:
        service = WizardService(session, InMemoryOrchestrator())
        project = await service.create_project(CreateWizardProjectRequest(name="third writer"))
        await service.update_scope(project.wizard_project_id, {"domains": ["example.com"]})
        await service.update_discovery_plan(
            project.wizard_project_id,
            {"source_id": source_id, "source_version_id": sv_id},
        )
        wizard_run = await service._get_latest_run_for_project(project.wizard_project_id)
        wizard_run_id = wizard_run.wizard_run_id
        await session.commit()

    shard_acts = ScopeShardActivities(session_factory=session_maker)

    async with session_maker() as session:
        service = WizardService(session, InMemoryOrchestrator())
        # Warm this session's identity map *before* the shard writes, so the
        # in-memory `progress` is stale by the time `start_pilot_run` gets to it.
        # That is the interleaving: a snapshot read, then somebody else's commit,
        # then a write built on the snapshot.
        await service.get_run(wizard_run_id)

        await shard_acts.report_shard_progress(
            wizard_run_id, "ch/zurich", {"nodes_discovered": 3, "records_accepted": 2}
        )

        await service.start_pilot_run(project.wizard_project_id, sample_limit=25)

    async with session_maker() as session:
        run = await session.get(WizardRun, wizard_run_id)
        assert run is not None
        assert run.progress["sample_limit"] == 25
        assert "ch/zurich" in run.progress["shards"], "the shard's entry was clobbered"
        assert run.progress["accepted_records"] == 2
        # Both writers bumped the version, so a third could detect either of them.
        assert run.progress_version == 2


@pytest.mark.asyncio
async def test_a_different_shard_of_the_same_run_still_gets_its_own_run(session_maker) -> None:
    """The key is per shard: deduping must not collapse the fan-out into one crawl."""
    wizard_run_id = await _wizard_run_with_source(session_maker, "per-shard")
    provider = _CountingProvider()
    registry = ProviderRegistry()
    registry.register(provider)
    shard_acts = ScopeShardActivities(
        session_factory=session_maker,
        provider_registry_factory=lambda: registry,
    )

    zurich = await shard_acts.run_shard_crawl(wizard_run_id, "ch/zurich", None)
    bern = await shard_acts.run_shard_crawl(wizard_run_id, "ch/bern", None)

    assert provider.dispatches == 2
    assert zurich["run_id"] != bern["run_id"]


@pytest.mark.asyncio
async def test_shard_progress_reports_survive_each_other_and_their_own_retries(
    session_maker,
) -> None:
    """#561: concurrent shard completions must both land, and a retry must not double-count.

    The deterministic proof of the compare-and-set lives in
    `test_wizard_progress_store.py`; this is the activity-level end-to-end.
    """
    wizard_run_id = await _wizard_run_with_source(session_maker, "progress")
    shard_acts = ScopeShardActivities(session_factory=session_maker)

    stats = {"nodes_discovered": 4, "records_accepted": 3, "records_sent_to_review": 1}
    await asyncio.gather(
        *[
            shard_acts.report_shard_progress(wizard_run_id, key, stats)
            for key in ("ch/zurich", "ch/bern", "ch/aargau")
        ]
    )
    # Temporal retries this activity up to three times; the same report arriving
    # twice must not inflate the aggregate.
    await shard_acts.report_shard_progress(wizard_run_id, "ch/zurich", stats)

    async with session_maker() as session:
        run = await session.get(WizardRun, wizard_run_id)
        assert run is not None
        assert set(run.progress["shards"]) == {"ch/zurich", "ch/bern", "ch/aargau"}
        assert run.progress["total_nodes"] == 12
        assert run.progress["accepted_records"] == 9
        assert run.progress["routed_to_review"] == 3
