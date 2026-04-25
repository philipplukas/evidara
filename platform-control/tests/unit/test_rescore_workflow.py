"""Coverage for ``RescoreActivities`` + ``RescoreCorrectionWorkflow``.

The Temporal ephemeral test server isn't reachable in the default sandbox
(see ``conftest.pytest_collection_modifyitems``), so the workflow's
sequencing is exercised directly against the activity callables instead of
through ``WorkflowEnvironment``. The full replay-based test is still
present and marked ``requires_network`` so the CI lane that opts in still
runs it.
"""

from __future__ import annotations

import pytest
from sqlalchemy.ext.asyncio import AsyncSession, async_sessionmaker

from platform_control.domain import CorrectionStatus, CorrectionType
from platform_control.models.correction import Correction
from platform_control.schemas.correction import RescoreRequest
from platform_control.services.correction_service import CorrectionService
from platform_control.temporal.activities import RescoreActivities


async def _seed_rescore_row(
    session_maker: async_sessionmaker[AsyncSession],
    *,
    before: dict | None = None,
    after: dict | None = None,
) -> str:
    """Return the rescore_correction_id of a freshly-seeded rescore row."""
    async with session_maker() as session:
        source = Correction(
            correction_type=CorrectionType.FIELD_EDIT,
            target_entity_type="commentary_insight",
            target_entity_id="ci_workflow",
            payload={
                "before": before if before is not None else {"jurisdiction": "DE"},
                "after": after if after is not None else {"jurisdiction": "CH"},
            },
        )
        session.add(source)
        await session.commit()
        await session.refresh(source)

    async with session_maker() as session:
        service = CorrectionService(session)
        response = await service.request_rescore(source.correction_id, RescoreRequest())
    return response.rescore_correction_id


@pytest.mark.asyncio
async def test_resolve_correction_returns_target_and_payload(session_maker) -> None:
    rescore_id = await _seed_rescore_row(session_maker)
    activities = RescoreActivities(session_factory=session_maker)
    resolved = await activities.resolve_correction(rescore_id)

    assert resolved["rescore_correction_id"] == rescore_id
    assert resolved["target_entity_type"] == "commentary_insight"
    assert resolved["target_entity_id"] == "ci_workflow"
    assert resolved["dry_run"] is False
    assert resolved["source_payload"]["after"] == {"jurisdiction": "CH"}


@pytest.mark.asyncio
async def test_resolve_correction_unknown_raises(session_maker) -> None:
    activities = RescoreActivities(session_factory=session_maker)
    with pytest.raises(RuntimeError):
        await activities.resolve_correction("corr_missing")


@pytest.mark.asyncio
async def test_load_target_entity_returns_baseline_from_source(session_maker) -> None:
    activities = RescoreActivities(session_factory=session_maker)
    baseline = await activities.load_target_entity(
        "commentary_insight",
        "ci_workflow",
        {"before": {"jurisdiction": "DE"}, "after": {"jurisdiction": "CH"}},
    )
    assert baseline == {"baseline": {"jurisdiction": "DE"}}


@pytest.mark.asyncio
async def test_invoke_targeted_extraction_uses_injected_extractor(
    session_maker,
) -> None:
    captured = {}

    def fake_extractor(**kwargs):
        captured.update(kwargs)
        return {
            "target_entity_type": kwargs["target_entity_type"],
            "target_entity_id": kwargs["target_entity_id"],
            "extraction_id": "ext_fake",
            "fields": {"jurisdiction": "CH"},
            "diff": {"jurisdiction": {"before": "DE", "after": "CH"}},
            "outcome": "changed",
        }

    activities = RescoreActivities(session_factory=session_maker, targeted_extractor=fake_extractor)
    result = await activities.invoke_targeted_extraction(
        "commentary_insight",
        "ci_workflow",
        {"jurisdiction": "DE"},
        {"after": {"jurisdiction": "CH"}},
        False,
    )
    assert result["outcome"] == "changed"
    assert captured["target_entity_id"] == "ci_workflow"


@pytest.mark.asyncio
async def test_diff_against_baseline_normalises_outcome(session_maker) -> None:
    activities = RescoreActivities(session_factory=session_maker)
    diffed = await activities.diff_against_baseline(
        {
            "outcome": "totally_unknown",
            "diff": {"a": 1},
            "extraction_id": "ext_foo",
            "fields": {},
        }
    )
    assert diffed["outcome"] == "failed"
    diffed_changed = await activities.diff_against_baseline(
        {
            "outcome": "changed",
            "diff": {"a": 1},
            "extraction_id": "ext_foo",
        }
    )
    assert diffed_changed["outcome"] == "changed"


@pytest.mark.asyncio
async def test_record_outcome_writes_terminal_status_and_runs_metric_callback(
    session_maker,
) -> None:
    rescore_id = await _seed_rescore_row(session_maker)
    metrics: list[tuple[str, dict]] = []

    activities = RescoreActivities(
        session_factory=session_maker,
        metrics_callback=lambda name, fields: metrics.append((name, fields)),
    )
    await activities.record_outcome(
        rescore_id,
        "changed",
        {"jurisdiction": {"before": "DE", "after": "CH"}},
        "ext_foo",
        "run_done_001",
        None,
    )

    async with session_maker() as session:
        rescore = await session.get(Correction, rescore_id)
        assert rescore is not None
        assert rescore.status is CorrectionStatus.CHANGED
        assert rescore.resulting_run_id == "run_done_001"
        assert rescore.resulting_extraction_id == "ext_foo"

    assert metrics == [
        (
            "correction.rescore",
            {
                "outcome": "changed",
                "target_entity_type": "commentary_insight",
                "target_entity_id": "ci_workflow",
                "resulting_run_id": "run_done_001",
                "extraction_id": "ext_foo",
            },
        )
    ]


@pytest.mark.asyncio
async def test_record_outcome_failed_carries_error_field(session_maker) -> None:
    rescore_id = await _seed_rescore_row(session_maker)
    activities = RescoreActivities(session_factory=session_maker)
    await activities.record_outcome(
        rescore_id,
        "failed",
        {},
        None,
        None,
        "extractor blew up",
    )
    async with session_maker() as session:
        rescore = await session.get(Correction, rescore_id)
        assert rescore is not None
        assert rescore.status is CorrectionStatus.FAILED
        assert rescore.payload["outcome_log"][-1]["error"] == "extractor blew up"


@pytest.mark.asyncio
async def test_record_outcome_invalid_outcome_falls_back_to_failed(session_maker) -> None:
    rescore_id = await _seed_rescore_row(session_maker)
    activities = RescoreActivities(session_factory=session_maker)
    await activities.record_outcome(rescore_id, "made_up_outcome", {}, None, None, None)
    async with session_maker() as session:
        rescore = await session.get(Correction, rescore_id)
        assert rescore is not None
        assert rescore.status is CorrectionStatus.FAILED


@pytest.mark.asyncio
async def test_full_activity_chain_drives_changed_outcome(session_maker) -> None:
    """End-to-end activity composition without booting Temporal.

    Mirrors the ordering ``RescoreCorrectionWorkflow.run`` enforces:
    resolve → load_target_entity → invoke_targeted_extraction → diff →
    record_outcome.
    """
    rescore_id = await _seed_rescore_row(session_maker)

    def extractor(*, target_entity_type, target_entity_id, baseline, correction_payload):
        new = dict(correction_payload.get("after") or {})
        diff = {
            k: {"before": baseline.get(k), "after": v}
            for k, v in new.items()
            if baseline.get(k) != v
        }
        return {
            "target_entity_type": target_entity_type,
            "target_entity_id": target_entity_id,
            "extraction_id": "ext_chain",
            "fields": new,
            "diff": diff,
            "outcome": "changed" if diff else "unchanged",
        }

    activities = RescoreActivities(session_factory=session_maker, targeted_extractor=extractor)
    resolved = await activities.resolve_correction(rescore_id)
    baseline = (
        await activities.load_target_entity(
            resolved["target_entity_type"],
            resolved["target_entity_id"],
            resolved["source_payload"],
        )
    )["baseline"]
    extraction = await activities.invoke_targeted_extraction(
        resolved["target_entity_type"],
        resolved["target_entity_id"],
        baseline,
        resolved["source_payload"],
        resolved["dry_run"],
    )
    diffed = await activities.diff_against_baseline(extraction)
    await activities.record_outcome(
        rescore_id,
        diffed["outcome"],
        diffed["diff"],
        diffed["extraction_id"],
        None,
        diffed.get("error"),
    )

    async with session_maker() as session:
        rescore = await session.get(Correction, rescore_id)
        assert rescore is not None
        assert rescore.status is CorrectionStatus.CHANGED
        assert rescore.resulting_extraction_id == "ext_chain"


@pytest.mark.asyncio
async def test_activity_chain_drives_unchanged_when_baseline_matches(
    session_maker,
) -> None:
    """When the extractor's output matches the baseline the outcome is unchanged."""
    rescore_id = await _seed_rescore_row(
        session_maker,
        before={"jurisdiction": "CH"},
        after={"jurisdiction": "CH"},
    )

    def extractor(*, target_entity_type, target_entity_id, baseline, correction_payload):
        del correction_payload
        # Echo baseline so diff is empty.
        return {
            "target_entity_type": target_entity_type,
            "target_entity_id": target_entity_id,
            "extraction_id": "ext_noop",
            "fields": dict(baseline),
            "diff": {},
            "outcome": "unchanged",
        }

    activities = RescoreActivities(session_factory=session_maker, targeted_extractor=extractor)
    resolved = await activities.resolve_correction(rescore_id)
    baseline = (
        await activities.load_target_entity(
            resolved["target_entity_type"],
            resolved["target_entity_id"],
            resolved["source_payload"],
        )
    )["baseline"]
    extraction = await activities.invoke_targeted_extraction(
        resolved["target_entity_type"],
        resolved["target_entity_id"],
        baseline,
        resolved["source_payload"],
        resolved["dry_run"],
    )
    diffed = await activities.diff_against_baseline(extraction)
    await activities.record_outcome(
        rescore_id,
        diffed["outcome"],
        diffed["diff"],
        diffed["extraction_id"],
        None,
        None,
    )

    async with session_maker() as session:
        rescore = await session.get(Correction, rescore_id)
        assert rescore is not None
        assert rescore.status is CorrectionStatus.UNCHANGED


@pytest.mark.asyncio
async def test_activity_chain_drives_failed_when_extractor_raises(session_maker) -> None:
    rescore_id = await _seed_rescore_row(session_maker)

    def boom(**kwargs):
        raise RuntimeError("oh no")

    # The activity itself doesn't catch — invoke_targeted_extraction surfaces
    # the failure to the workflow, which then records "failed".
    activities = RescoreActivities(session_factory=session_maker, targeted_extractor=boom)
    resolved = await activities.resolve_correction(rescore_id)
    baseline = (
        await activities.load_target_entity(
            resolved["target_entity_type"],
            resolved["target_entity_id"],
            resolved["source_payload"],
        )
    )["baseline"]
    with pytest.raises(RuntimeError):
        await activities.invoke_targeted_extraction(
            resolved["target_entity_type"],
            resolved["target_entity_id"],
            baseline,
            resolved["source_payload"],
            False,
        )
    # Workflow's except branch records "failed" — exercise that directly.
    await activities.record_outcome(
        rescore_id,
        "failed",
        {},
        None,
        None,
        "oh no",
    )
    async with session_maker() as session:
        rescore = await session.get(Correction, rescore_id)
        assert rescore is not None
        assert rescore.status is CorrectionStatus.FAILED


@pytest.mark.asyncio
@pytest.mark.requires_network
async def test_rescore_workflow_replay_full_run(session_maker) -> None:
    """Optional Temporal-backed coverage; opt in via PYTEST_NETWORK_TESTS=1.

    Exercises ``RescoreCorrectionWorkflow`` via the Temporal test server so
    the workflow ordering, retries, and child activity invocation are all
    validated together.
    """
    from temporalio.client import WorkflowFailureError
    from temporalio.testing import WorkflowEnvironment
    from temporalio.worker import Worker

    from platform_control.temporal.workflows import RescoreCorrectionWorkflow

    rescore_id = await _seed_rescore_row(session_maker)

    def extractor(*, target_entity_type, target_entity_id, baseline, correction_payload):
        new = dict(correction_payload.get("after") or {})
        diff = {
            k: {"before": baseline.get(k), "after": v}
            for k, v in new.items()
            if baseline.get(k) != v
        }
        return {
            "target_entity_type": target_entity_type,
            "target_entity_id": target_entity_id,
            "extraction_id": "ext_replay",
            "fields": new,
            "diff": diff,
            "outcome": "changed" if diff else "unchanged",
        }

    activities = RescoreActivities(session_factory=session_maker, targeted_extractor=extractor)
    async with await WorkflowEnvironment.start_time_skipping() as env:
        async with Worker(
            env.client,
            task_queue="rescore-test",
            workflows=[RescoreCorrectionWorkflow],
            activities=[
                activities.resolve_correction,
                activities.load_target_entity,
                activities.invoke_targeted_extraction,
                activities.diff_against_baseline,
                activities.record_outcome,
            ],
        ):
            try:
                outcome = await env.client.execute_workflow(
                    RescoreCorrectionWorkflow.run,
                    rescore_id,
                    id=f"replay-{rescore_id}",
                    task_queue="rescore-test",
                )
            except WorkflowFailureError as exc:
                pytest.fail(f"workflow failed: {exc}")

    assert outcome == "changed"
    async with session_maker() as session:
        rescore = await session.get(Correction, rescore_id)
        assert rescore is not None
        assert rescore.status is CorrectionStatus.CHANGED
        assert rescore.resulting_extraction_id == "ext_replay"
