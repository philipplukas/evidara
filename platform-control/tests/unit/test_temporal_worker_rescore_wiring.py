"""Activity-level smoke for the rescore worker wire-up (#450, M11/A1).

Covers the contract A1 introduces:
- `InMemoryRescoreRunner` returns the deterministic "unchanged" outcome.
- `RescoreFromCorrectionActivities` invokes the runner factory and
  persists the outcome on the correction payload.
- The temporal worker module exposes the activity + workflow registration
  alongside the in-memory runner factory (asserted by inspecting the
  imports — full Temporal worker boot needs a real server).

A2 (#451) replaces `InMemoryRescoreRunner` with the real DI-side impl.
"""

from __future__ import annotations

import pytest
from sqlalchemy.ext.asyncio import AsyncSession, async_sessionmaker

from platform_control.schemas.correction import (
    CorrectionType,
    CreateCorrectionRequest,
    TargetEntityType,
)
from platform_control.services.correction_service import CorrectionService
from platform_control.temporal.activities import RescoreFromCorrectionActivities
from platform_control.temporal.runners import InMemoryRescoreRunner

_DOCUMENT_ID = "doc_01jq7bdptzqv3xs0c41xpw1ybg"
_OPERATOR = "op_01jqs7p1bcvz2tw5kxh9mq80fg"


@pytest.mark.asyncio
async def test_in_memory_runner_returns_unchanged_outcome() -> None:
    runner = InMemoryRescoreRunner()
    outcome, run_id = await runner.run_targeted_rescore(
        target_entity_type="document",
        target_entity_id=_DOCUMENT_ID,
        correction_id="cor_01jq7000000000000000000000",
    )
    assert outcome == "unchanged"
    assert run_id is None


@pytest.mark.asyncio
async def test_activity_persists_unchanged_outcome_via_in_memory_runner(
    session: AsyncSession,
    session_maker: async_sessionmaker[AsyncSession],
) -> None:
    service = CorrectionService(session)
    correction = await service.create(
        CreateCorrectionRequest(
            target_entity_type=TargetEntityType.DOCUMENT,
            target_entity_id=_DOCUMENT_ID,
            correction_type=CorrectionType.RESCORE_REQUEST,
            payload={"reason_code": "low_quality_extractions"},
        ),
        operator_id=_OPERATOR,
    )
    await session.commit()

    activities = RescoreFromCorrectionActivities(
        session_factory=session_maker,
        rescore_runner_factory=InMemoryRescoreRunner,
    )

    result = await activities.run_targeted_rescore(
        {
            "correction_id": correction.correction_id,
            "target_entity_type": "document",
            "target_entity_id": _DOCUMENT_ID,
        },
    )

    assert result["outcome"] == "unchanged"
    assert result["resulting_run_id"] is None

    # The activity opened its own session via session_maker and committed
    # the outcome; read back through a fresh session to confirm.
    async with session_maker() as fresh:
        refreshed = await CorrectionService(fresh).get(correction.correction_id)
    assert refreshed.payload["rescore_outcome"] == "unchanged"
    assert refreshed.payload["completed_at"] is not None


def test_temporal_worker_registers_rescore_activity_and_workflow() -> None:
    """Sanity-check the worker module wires the rescore artefacts.

    Full worker boot requires a Temporal server; this test just confirms
    the production module imports the right symbols so a future refactor
    that drops the activity registration trips immediately.
    """
    from platform_control import temporal_worker

    source = (
        __import__("inspect").getsource(temporal_worker._async_main)  # type: ignore[attr-defined]
    )
    assert "RescoreFromCorrectionActivities" in source
    assert "RescoreFromCorrectionWorkflow" in source
    assert "InMemoryRescoreRunner" in source
    assert "rescore_acts.run_targeted_rescore" in source
