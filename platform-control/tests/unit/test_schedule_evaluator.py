from __future__ import annotations

import pytest

from platform_control.domain import ExecutionMode, RunMode
from platform_control.models.authority import Authority, Jurisdiction
from platform_control.models.schedule import Schedule
from platform_control.models.source import Source
from platform_control.models.source_version import SourceVersion
from platform_control.services.schedule_evaluator import evaluate_due_schedules


async def _seed_source_with_version(
    session, *, execution_mode: ExecutionMode
) -> tuple[Source, SourceVersion]:
    session.add(Jurisdiction(jurisdiction_id="jur_ch", name="Switzerland", slug="ch"))
    session.add(
        Authority(
            authority_id="auth_zh_admin",
            jurisdiction_id="jur_ch",
            name="Zurich Administrative Court",
            slug="zh-admin-court",
        )
    )
    await session.flush()

    source = Source(
        name="Zurich decisions",
        jurisdiction_id="jur_ch",
        authority_id="auth_zh_admin",
    )
    session.add(source)
    await session.flush()

    version = SourceVersion(
        source_id=source.source_id,
        version_label="v1",
        execution_mode=execution_mode,
        acquisition_spec={
            "provider": "deterministic_http",
            "seed_urls": ["https://example.com/"],
        },
    )
    session.add(version)
    await session.commit()
    return source, version


@pytest.mark.asyncio
async def test_evaluator_fires_due_schedule_for_live_source_version(session) -> None:
    _, version = await _seed_source_with_version(session, execution_mode=ExecutionMode.LIVE)
    session.add(
        Schedule(
            source_id=version.source_id,
            source_version_id=version.source_version_id,
            cron_expression="* * * * *",
            mode=RunMode.PRODUCTION,
            enabled=True,
        )
    )
    await session.commit()

    created = await evaluate_due_schedules(session)

    assert created == 1


@pytest.mark.asyncio
async def test_evaluator_skips_due_schedule_when_execution_mode_off(session) -> None:
    _, version = await _seed_source_with_version(session, execution_mode=ExecutionMode.OFF)
    session.add(
        Schedule(
            source_id=version.source_id,
            source_version_id=version.source_version_id,
            cron_expression="* * * * *",
            mode=RunMode.PRODUCTION,
            enabled=True,
        )
    )
    await session.commit()

    created = await evaluate_due_schedules(session)

    assert created == 0


@pytest.mark.asyncio
async def test_evaluator_runs_shadow_schedule(session) -> None:
    """Shadow routes through the scheduler so the workflow path is exercised."""
    _, version = await _seed_source_with_version(session, execution_mode=ExecutionMode.SHADOW)
    session.add(
        Schedule(
            source_id=version.source_id,
            source_version_id=version.source_version_id,
            cron_expression="* * * * *",
            mode=RunMode.PRODUCTION,
            enabled=True,
        )
    )
    await session.commit()

    created = await evaluate_due_schedules(session)

    assert created == 1


def test_an_acceptance_run_cannot_be_scheduled() -> None:
    """A rehearsal must not become a cron (#743 review).

    `RunMode.ACCEPTANCE` reaches a live portal on a provider with no acceptance
    evidence, and for an AWAITING_EVIDENCE provider it waives the operator's
    config key. `evaluate_due_schedules` stamps the schedule's mode straight onto
    a Run without passing `_require_launchable`, so a scheduled acceptance run
    would be permanent unattended crawling that the kill switch cannot stop.
    The schema boundary is the only place that can refuse it.
    """
    import pytest as _pytest
    from pydantic import ValidationError

    from platform_control.schemas.schedule import CreateScheduleRequest, UpdateScheduleRequest

    with _pytest.raises(ValidationError, match="cannot be scheduled"):
        CreateScheduleRequest(
            source_id="src_1",
            source_version_id="sv_1",
            cron_expression="*/5 * * * *",
            mode=RunMode.ACCEPTANCE,
        )

    # PATCHing an existing schedule is the same hole from the other side.
    with _pytest.raises(ValidationError, match="cannot be scheduled"):
        UpdateScheduleRequest(mode=RunMode.ACCEPTANCE)

    # The modes that were always schedulable still are.
    assert (
        CreateScheduleRequest(
            source_id="src_1",
            source_version_id="sv_1",
            cron_expression="*/5 * * * *",
            mode=RunMode.PREVIEW,
        ).mode
        is RunMode.PREVIEW
    )
