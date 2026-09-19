"""The reclaim sweep and its console script (#1038).

What has to be true, and each test names the mutation that breaks it:

* a unit that went quiet past the deadline gets a terminal row, written by the
  control plane rather than by the worker that died;
* a unit still inside the deadline does not;
* a unit that already terminated is never touched, so a quarantine or a reported
  failure cannot be overwritten;
* running twice writes one row;
* the row says what it knows and does not invent a cause.
"""

from __future__ import annotations

import asyncio
import re
from datetime import UTC, datetime, timedelta

import pytest
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession, async_sessionmaker

from platform_control import processing_reclaim
from platform_control.domain import (
    ProcessingReconciliationVerdict,
    ProcessingStatus,
    RunMode,
    RunStatus,
    SourceVersionStatus,
)
from platform_control.models.authority import Authority, Jurisdiction
from platform_control.models.compliance_policy import CompliancePolicy
from platform_control.models.processing_status_update import ProcessingStatusUpdate
from platform_control.models.run import Run
from platform_control.models.source import Source
from platform_control.models.source_version import SourceVersion
from platform_control.services.processing_reclaim_service import (
    PROCESSING_DEADLINE_EXCEEDED,
    ProcessingReclaimService,
    reclaim_event_id,
)
from platform_control.services.processing_reconciliation import reconcile_processing

NOW = datetime(2026, 9, 19, 12, 0, tzinfo=UTC)
#: The oldest stranded row measured in production, 8d22h before NOW.
STRANDED_AT = datetime(2026, 9, 10, 18, 49, 37, tzinfo=UTC)

#: The two runs the issue names. Both report `status=completed`; between them they
#: held 116 documents that never reached a terminal processing status.
RUN_A = "run_01m26a84j0gdmeh9g5f8b1k36k"
RUN_B = "run_01m2q5fsqmarc3mxvfpsw1jjdt"


async def _seed_runs(session: AsyncSession) -> None:
    policy = CompliancePolicy(compliance_policy_id="cp_reclaim", name="ch-reclaim")
    session.add(policy)
    session.add(
        Jurisdiction(
            jurisdiction_id="jur_ch_zh",
            name="Zurich",
            slug="ch-zh",
            compliance_policy_id="cp_reclaim",
        )
    )
    session.add(
        Authority(
            authority_id="auth_zh",
            jurisdiction_id="jur_ch_zh",
            name="Kanton Zurich",
            slug="ch-zh-kanton",
        )
    )
    session.add(
        Source(
            source_id="src_zh",
            name="ZH LexFind",
            jurisdiction_id="jur_ch_zh",
            authority_id="auth_zh",
        )
    )
    session.add(
        SourceVersion(
            source_version_id="sv_zh",
            source_id="src_zh",
            version_label="v1",
            status=SourceVersionStatus.APPROVED,
            acquisition_spec={"provider": "lexfind_api"},
        )
    )
    for run_id in (RUN_A, RUN_B):
        session.add(
            Run(
                run_id=run_id,
                source_id="src_zh",
                source_version_id="sv_zh",
                mode=RunMode.ACCEPTANCE,
                # Both runs report completed. That is the point.
                status=RunStatus.COMPLETED,
                completed_at=STRANDED_AT,
            )
        )
    await session.commit()


def _status_row(
    *,
    event_id: str,
    run_id: str,
    unit: str,
    status: ProcessingStatus,
    occurred_at: datetime,
    document_id: str | None = None,
    error_code: str | None = None,
    error_summary: str | None = None,
) -> ProcessingStatusUpdate:
    return ProcessingStatusUpdate(
        event_id=event_id,
        run_id=run_id,
        processing_manifest_id=unit,
        processing_version="2026.09",
        status=status,
        occurred_at=occurred_at,
        source_snapshot_id="snap_zh",
        bundle_manifest_id="abm_zh",
        document_id=document_id,
        document_revision=1 if document_id else None,
        error_code=error_code,
        error_summary=error_summary,
    )


async def _add_stranded_unit(
    session: AsyncSession,
    *,
    run_id: str,
    index: int,
    at: datetime = STRANDED_AT,
) -> str:
    """The production fingerprint: `accepted` + `processing`, and then silence."""
    unit = f"pm_stranded_{run_id[-4:]}_{index}"
    session.add(
        _status_row(
            event_id=f"evt_acc_{unit}",
            run_id=run_id,
            unit=unit,
            status=ProcessingStatus.ACCEPTED,
            occurred_at=at,
            document_id=f"doc_{unit}",
        )
    )
    session.add(
        _status_row(
            event_id=f"evt_proc_{unit}",
            run_id=run_id,
            unit=unit,
            status=ProcessingStatus.PROCESSING,
            occurred_at=at + timedelta(seconds=1),
            document_id=f"doc_{unit}",
        )
    )
    await session.commit()
    return unit


async def _rows_for(session: AsyncSession, run_id: str) -> list[ProcessingStatusUpdate]:
    return list(
        await session.scalars(
            select(ProcessingStatusUpdate).where(ProcessingStatusUpdate.run_id == run_id)
        )
    )


@pytest.mark.asyncio
async def test_reclaim_terminates_a_unit_that_went_quiet_past_the_deadline(
    session: AsyncSession,
) -> None:
    """The headline: a stranded unit ends up terminal, and the run reconciles.

    MUTATION: delete the `_write_terminal_row` call from `reclaim` and this fails
    on the verdict — the run stays `UNTERMINATED` forever, which is exactly the
    state production was in for nine days.
    """
    await _seed_runs(session)
    unit = await _add_stranded_unit(session, run_id=RUN_A, index=0)

    before = reconcile_processing(await _rows_for(session, RUN_A), now=NOW)
    assert before.verdict is ProcessingReconciliationVerdict.UNTERMINATED

    report = await ProcessingReclaimService(session).reclaim(now=NOW)

    assert report.units_examined == 1
    assert report.units_past_deadline == 1
    assert report.units_reclaimed == 1
    assert report.runs_touched == [RUN_A]

    after = reconcile_processing(await _rows_for(session, RUN_A), now=NOW)
    assert after.verdict is ProcessingReconciliationVerdict.RECONCILED
    assert after.is_clean is True

    written = [
        row for row in await _rows_for(session, RUN_A) if row.status is ProcessingStatus.FAILED
    ]
    assert len(written) == 1
    assert written[0].processing_manifest_id == unit
    assert written[0].error_code == PROCESSING_DEADLINE_EXCEEDED
    assert written[0].document_id == f"doc_{unit}"


@pytest.mark.asyncio
async def test_reclaim_leaves_work_inside_the_deadline_alone(session: AsyncSession) -> None:
    """Work still in flight must not be terminated.

    MUTATION: drop the `if unit.last_seen_at > cutoff: continue` guard in
    `reclaim` and this fails — a run dispatched five minutes ago would have every
    one of its documents marked failed.
    """
    await _seed_runs(session)
    await _add_stranded_unit(session, run_id=RUN_A, index=0, at=NOW - timedelta(minutes=5))

    report = await ProcessingReclaimService(session).reclaim(now=NOW)

    assert report.units_examined == 1
    assert report.units_past_deadline == 0
    assert report.units_reclaimed == 0
    assert not any(row.status is ProcessingStatus.FAILED for row in await _rows_for(session, RUN_A))


@pytest.mark.asyncio
async def test_reclaim_never_touches_a_unit_that_already_terminated(
    session: AsyncSession,
) -> None:
    """A quarantine or a reported failure is a decision; the sweep must not overwrite it.

    MUTATION: remove the `not_in(terminal_units)` filter from `_non_terminal_units`
    and this fails — both already-terminal units get a second, contradicting
    terminal row.
    """
    await _seed_runs(session)
    for unit, status in (
        ("pm_quarantined", ProcessingStatus.QUARANTINED),
        ("pm_reported_failure", ProcessingStatus.FAILED),
    ):
        session.add(
            _status_row(
                event_id=f"evt_acc_{unit}",
                run_id=RUN_A,
                unit=unit,
                status=ProcessingStatus.ACCEPTED,
                occurred_at=STRANDED_AT,
                document_id=f"doc_{unit}",
            )
        )
        session.add(
            _status_row(
                event_id=f"evt_term_{unit}",
                run_id=RUN_A,
                unit=unit,
                status=status,
                occurred_at=STRANDED_AT + timedelta(seconds=2),
                document_id=f"doc_{unit}",
                error_code="no_text_layer",
                error_summary="PDF has no text layer.",
            )
        )
    await session.commit()

    report = await ProcessingReclaimService(session).reclaim(now=NOW)

    assert report.units_examined == 0
    assert report.units_reclaimed == 0
    assert not any(
        row.error_code == PROCESSING_DEADLINE_EXCEEDED for row in await _rows_for(session, RUN_A)
    )


@pytest.mark.asyncio
async def test_reclaim_is_idempotent_across_passes(session: AsyncSession) -> None:
    """Two sweeps write one terminal row, not two.

    MUTATION: make `reclaim_event_id` random (e.g. `generate_prefixed_id("evt")`)
    and the deterministic-id half of this stops holding. The terminal-status filter
    still catches the sequential case, so the assertion that matters is the direct
    one below: the same unit always resolves to the same event id.
    """
    await _seed_runs(session)
    unit = await _add_stranded_unit(session, run_id=RUN_A, index=0)

    first = await ProcessingReclaimService(session).reclaim(now=NOW)
    second = await ProcessingReclaimService(session).reclaim(now=NOW + timedelta(hours=1))

    assert first.units_reclaimed == 1
    assert second.units_examined == 0
    assert second.units_reclaimed == 0

    failed = [
        row for row in await _rows_for(session, RUN_A) if row.status is ProcessingStatus.FAILED
    ]
    assert len(failed) == 1
    assert failed[0].event_id == reclaim_event_id(unit)
    assert reclaim_event_id(unit) == reclaim_event_id(unit)


@pytest.mark.asyncio
async def test_a_concurrent_second_writer_is_recorded_as_a_duplicate(
    session: AsyncSession,
) -> None:
    """The deterministic id is what makes a race harmless.

    A manual backfill running beside the CronJob would otherwise write two
    terminal rows for one unit. The row pre-inserted here carries the id the sweep
    will mint and a NON-terminal status, so the unit is still selected and the
    insert really does reach the primary key — the inner guard, not the outer one.

    MUTATION: make `reclaim_event_id` random and this fails: the insert succeeds
    and the unit ends up with two rows claiming to be its terminal one.
    """
    await _seed_runs(session)
    unit = await _add_stranded_unit(session, run_id=RUN_A, index=0)
    session.add(
        _status_row(
            event_id=reclaim_event_id(unit),
            run_id=RUN_A,
            unit=unit,
            status=ProcessingStatus.PROCESSING,
            occurred_at=STRANDED_AT + timedelta(seconds=2),
            document_id=f"doc_{unit}",
        )
    )
    await session.commit()

    report = await ProcessingReclaimService(session).reclaim(now=NOW)

    assert report.units_past_deadline == 1
    assert report.units_reclaimed == 0
    assert report.duplicates == 1
    rows = await _rows_for(session, RUN_A)
    assert sum(1 for row in rows if row.event_id == reclaim_event_id(unit)) == 1


@pytest.mark.asyncio
async def test_dry_run_reports_the_count_and_writes_nothing(session: AsyncSession) -> None:
    """`--dry-run` must still distinguish "found nothing" from "declined to act".

    MUTATION: make `dry_run` skip the loop entirely and `units_past_deadline`
    drops to 0, which reads as a clean estate.
    """
    await _seed_runs(session)
    await _add_stranded_unit(session, run_id=RUN_A, index=0)
    await _add_stranded_unit(session, run_id=RUN_A, index=1)

    report = await ProcessingReclaimService(session).reclaim(now=NOW, dry_run=True)

    assert report.dry_run is True
    assert report.units_examined == 2
    assert report.units_past_deadline == 2
    assert report.units_reclaimed == 0
    assert report.runs_touched == [RUN_A]
    assert not any(row.status is ProcessingStatus.FAILED for row in await _rows_for(session, RUN_A))


@pytest.mark.asyncio
async def test_the_reclaimed_row_refuses_to_invent_a_cause(session: AsyncSession) -> None:
    """The summary must say who wrote it and that the cause is unknown.

    A terminal status that silently implies document-intelligence reported a
    failure is the same defect wearing the opposite mask: DI reported nothing,
    which is the problem.
    """
    await _seed_runs(session)
    await _add_stranded_unit(session, run_id=RUN_A, index=0)

    await ProcessingReclaimService(session).reclaim(now=NOW)

    row = next(
        row for row in await _rows_for(session, RUN_A) if row.status is ProcessingStatus.FAILED
    )
    assert row.error_summary is not None
    summary = row.error_summary
    assert "reclaim sweep" in summary
    assert "not reported by document-intelligence" in summary
    assert "unknown" in summary
    # It names the evidence it does have: the last status and when it was seen.
    assert "`processing`" in summary
    assert "2026-09-10" in summary


@pytest.mark.asyncio
async def test_a_reclaimed_row_is_distinguishable_from_a_reported_failure(
    session: AsyncSession,
) -> None:
    """One error code separates "the control plane stopped waiting" from "DI failed".

    Without it, the two are one undifferentiated `failed` population and neither
    an operator nor a later reconciler can tell which is which.
    """
    await _seed_runs(session)
    await _add_stranded_unit(session, run_id=RUN_A, index=0)
    session.add(
        _status_row(
            event_id="evt_di_failure",
            run_id=RUN_A,
            unit="pm_di_failure",
            status=ProcessingStatus.FAILED,
            occurred_at=STRANDED_AT,
            document_id="doc_di_failure",
            error_code="normalize_error",
            error_summary="Docling raised on page 3.",
        )
    )
    await session.commit()

    await ProcessingReclaimService(session).reclaim(now=NOW)

    failures = [
        row for row in await _rows_for(session, RUN_A) if row.status is ProcessingStatus.FAILED
    ]
    codes = sorted(row.error_code or "" for row in failures)
    assert codes == ["normalize_error", PROCESSING_DEADLINE_EXCEEDED]


@pytest.mark.asyncio
async def test_reclaim_scoped_to_one_run_leaves_the_other_alone(session: AsyncSession) -> None:
    """`--run-id` narrows the sweep; the backfill runs it per run before it runs wide."""
    await _seed_runs(session)
    await _add_stranded_unit(session, run_id=RUN_A, index=0)
    await _add_stranded_unit(session, run_id=RUN_B, index=0)

    report = await ProcessingReclaimService(session).reclaim(now=NOW, run_id=RUN_A)

    assert report.units_reclaimed == 1
    assert report.runs_touched == [RUN_A]
    assert reconcile_processing(await _rows_for(session, RUN_A), now=NOW).is_clean is True
    assert reconcile_processing(await _rows_for(session, RUN_B), now=NOW).is_clean is False


@pytest.mark.asyncio
async def test_both_stranded_runs_reconcile_after_one_unscoped_sweep(
    session: AsyncSession,
) -> None:
    """The backfill, at the scale the issue reports: 58 units in each of two runs.

    Both runs report `completed` and both hold documents nothing downstream ever
    saw. One sweep terminates all 116.
    """
    await _seed_runs(session)
    for run_id in (RUN_A, RUN_B):
        for index in range(58):
            await _add_stranded_unit(session, run_id=run_id, index=index)

    report = await ProcessingReclaimService(session).reclaim(now=NOW)

    assert report.units_past_deadline == 116
    assert report.units_reclaimed == 116
    assert sorted(report.runs_touched) == sorted([RUN_A, RUN_B])
    for run_id in (RUN_A, RUN_B):
        assert reconcile_processing(await _rows_for(session, run_id), now=NOW).is_clean is True


def test_reclaim_event_id_has_the_shape_the_event_contract_declares() -> None:
    """`^evt_[0-9a-hjkmnp-tv-z]{26}$` — the pattern every other row in the table matches.

    A reclaimed row is never published as an event, but it lands in the same table
    as rows that were, and a reader should not have to special-case its shape.
    """
    pattern = re.compile(r"^evt_[0-9a-hjkmnp-tv-z]{26}$")
    for unit in ("pm_01m26a84j0gdmeh9g5f8b1k36k", "pm_x", "pm_" + "z" * 40):
        assert pattern.match(reclaim_event_id(unit)), reclaim_event_id(unit)
    assert reclaim_event_id("pm_a") != reclaim_event_id("pm_b")


def test_console_script_reclaims_and_prints_the_summary(
    session_maker: async_sessionmaker[AsyncSession],
    capsys: pytest.CaptureFixture[str],
) -> None:
    """The CronJob's command performs the sweep.

    Nothing is injected: `main` resolves the session factory from the environment
    exactly as it does inside the CronJob pod.
    """

    async def seed() -> None:
        async with session_maker() as session:
            await _seed_runs(session)
            await _add_stranded_unit(session, run_id=RUN_A, index=0)

    asyncio.run(seed())

    exit_code = processing_reclaim.main([])

    assert exit_code == 0
    out = capsys.readouterr().out
    assert "units_past_deadline=1" in out
    assert "units_reclaimed=1" in out


def test_console_script_dry_run_reports_without_writing(
    session_maker: async_sessionmaker[AsyncSession],
    capsys: pytest.CaptureFixture[str],
) -> None:
    async def seed() -> None:
        async with session_maker() as session:
            await _seed_runs(session)
            await _add_stranded_unit(session, run_id=RUN_A, index=0)

    async def failed_row_count() -> int:
        async with session_maker() as session:
            rows = await _rows_for(session, RUN_A)
            return sum(1 for row in rows if row.status is ProcessingStatus.FAILED)

    asyncio.run(seed())

    exit_code = processing_reclaim.main(["--dry-run"])

    assert exit_code == 0
    out = capsys.readouterr().out
    assert out.startswith("[dry-run] ")
    assert "units_past_deadline=1" in out
    assert "units_reclaimed=0" in out
    assert asyncio.run(failed_row_count()) == 0


def test_console_script_refuses_a_non_positive_deadline(
    session_maker: async_sessionmaker[AsyncSession],
) -> None:
    """A mistyped flag must fail, not quietly become "terminate everything".

    MUTATION: drop the `deadline_hours <= 0` check in `main` and this fails — the
    command becomes a way to mark every in-flight document failed.
    """
    assert processing_reclaim.main(["--deadline-hours", "0"]) == 2
    assert processing_reclaim.main(["--deadline-hours", "-1"]) == 2
