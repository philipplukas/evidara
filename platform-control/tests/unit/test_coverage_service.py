"""The acquisition-coverage aggregations, against a real (SQLite) session.

Each test pins one counting rule where the obvious implementation is wrong in a way that
would not look wrong: counting rows instead of URLs, events instead of documents, or
silently dropping the records an inner join cannot match.
"""

from __future__ import annotations

from datetime import UTC, datetime, timedelta

import pytest
from sqlalchemy.ext.asyncio import AsyncSession

from platform_control.domain import (
    CoverageAttributionStatus,
    DenominatorTier,
    NormLevel,
    RunMode,
    RunStatus,
)
from platform_control.models.authority import Authority, Jurisdiction
from platform_control.models.captured_resource import CapturedResource
from platform_control.models.coverage_reconciliation import CoverageReconciliation
from platform_control.models.document_lifecycle_event import DocumentLifecycleEvent
from platform_control.models.run import Run
from platform_control.models.source import Source
from platform_control.models.source_version import SourceVersion
from platform_control.services.coverage_service import CoverageService

_NOW = datetime(2026, 7, 28, 9, 0, tzinfo=UTC)


async def _seed(session: AsyncSession, *, jurisdiction_id: str = "jur_ch_zh") -> dict:
    session.add(
        Jurisdiction(
            jurisdiction_id=jurisdiction_id,
            name=f"Kanton {jurisdiction_id}",
            slug=jurisdiction_id.replace("_", "-"),
            level=NormLevel.CANTONAL,
        )
    )
    session.add(
        Authority(
            authority_id=f"auth_{jurisdiction_id}",
            jurisdiction_id=jurisdiction_id,
            name="Staatskanzlei",
            slug=f"sk-{jurisdiction_id}",
        )
    )
    source = Source(
        source_id=f"src_{jurisdiction_id}",
        name="LexFind",
        jurisdiction_id=jurisdiction_id,
        authority_id=f"auth_{jurisdiction_id}",
        source_type="api",
        document_family="law",
    )
    session.add(source)
    version = SourceVersion(
        source_version_id=f"sv_{jurisdiction_id}",
        source_id=source.source_id,
        version_label="v1",
    )
    session.add(version)
    run = Run(
        run_id=f"run_{jurisdiction_id}",
        source_id=source.source_id,
        source_version_id=version.source_version_id,
        mode=RunMode.ACCEPTANCE,
        status=RunStatus.COMPLETED,
    )
    session.add(run)
    await session.flush()
    return {"source": source, "version": version, "run": run}


def _captured(
    source_id: str, run_id: str, url: str, idx: int, *, version_id: str
) -> CapturedResource:
    return CapturedResource(
        captured_resource_id=f"cap_{idx:026d}",
        artifact_id=f"art_{idx:026d}",
        run_id=run_id,
        source_id=source_id,
        source_version_id=version_id,
        source_url=url,
        final_url=url,
        content_type="application/pdf",
    )


def _lifecycle(run_id: str, document_id: str, idx: int, event_type: str) -> DocumentLifecycleEvent:
    return DocumentLifecycleEvent(
        event_id=f"evt_{idx:026d}",
        event_type=event_type,
        run_id=run_id,
        document_id=document_id,
        document_revision=1,
        processing_manifest_id=f"pm_{idx:026d}",
        occurred_at=_NOW,
    )


@pytest.mark.asyncio
async def test_acquired_counts_distinct_urls_not_rows(session: AsyncSession) -> None:
    """Re-running a sweep must not inflate coverage.

    Two runs over the same law give two rows and one document. Counting rows would report
    2754 against a published 1377 and drive the gap negative for a reason that has nothing
    to do with coverage.
    """
    seeded = await _seed(session)
    src, run = seeded["source"].source_id, seeded["run"].run_id
    ver = seeded["version"].source_version_id
    session.add(_captured(src, run, "https://lexfind.ch/tol/22871/de", 1, version_id=ver))
    session.add(_captured(src, run, "https://lexfind.ch/tol/22871/de", 2, version_id=ver))
    await session.flush()

    payload = await CoverageService(session).get_acquisition_coverage()
    entry = next(e for e in payload["data"] if e["jurisdiction_id"] == "jur_ch_zh")
    assert entry["acquired_resources"] == 2
    assert entry["acquired_distinct_urls"] == 1


@pytest.mark.asyncio
async def test_processed_counts_distinct_documents_not_events(session: AsyncSession) -> None:
    """A reprocess emits a second event for the same document."""
    seeded = await _seed(session)
    run = seeded["run"].run_id
    session.add(_lifecycle(run, "doc_a", 1, "document.processed"))
    session.add(_lifecycle(run, "doc_a", 2, "document.processed"))
    await session.flush()

    payload = await CoverageService(session).get_acquisition_coverage()
    entry = next(e for e in payload["data"] if e["jurisdiction_id"] == "jur_ch_zh")
    assert entry["processed_documents"] == 1


@pytest.mark.asyncio
async def test_processed_events_for_unknown_runs_are_counted_not_dropped(
    session: AsyncSession,
) -> None:
    """`record_document_processed` never checks the run exists, so orphans are real.

    An inner join eats them silently. A document we processed but cannot attribute is a
    finding, not a rounding error.
    """
    await _seed(session)
    session.add(_lifecycle("run_does_not_exist", "doc_orphan", 9, "document.processed"))
    await session.flush()

    payload = await CoverageService(session).get_acquisition_coverage()
    assert payload["summary"]["processed_documents_unattributable"] == 1
    assert all(e["processed_documents"] == 0 for e in payload["data"])


@pytest.mark.asyncio
async def test_withdrawn_is_reported_separately_and_never_subtracted(
    session: AsyncSession,
) -> None:
    """`processed` means "DI confirmed processing at least once" — a statement about the
    pipeline, not about current holdings. A net figure would be invented."""
    seeded = await _seed(session)
    run = seeded["run"].run_id
    session.add(_lifecycle(run, "doc_a", 1, "document.processed"))
    session.add(_lifecycle(run, "doc_a", 2, "document.withdrawn"))
    await session.flush()

    payload = await CoverageService(session).get_acquisition_coverage()
    entry = next(e for e in payload["data"] if e["jurisdiction_id"] == "jur_ch_zh")
    assert entry["processed_documents"] == 1
    assert entry["withdrawn_documents"] == 1


@pytest.mark.asyncio
async def test_jurisdiction_without_a_reconciliation_reports_null_expected(
    session: AsyncSession,
) -> None:
    seeded = await _seed(session)
    session.add(
        _captured(
            seeded["source"].source_id,
            seeded["run"].run_id,
            "https://x/1",
            1,
            version_id=seeded["version"].source_version_id,
        )
    )
    await session.flush()

    payload = await CoverageService(session).get_acquisition_coverage()
    entry = next(e for e in payload["data"] if e["jurisdiction_id"] == "jur_ch_zh")
    assert entry["expected"] is None
    assert entry["denominator_tier"] is DenominatorTier.NONE
    assert entry["acquired_gap"] is None
    assert entry["acquired_distinct_urls"] == 1


@pytest.mark.asyncio
async def test_truncated_reconciliation_suppresses_gaps(session: AsyncSession) -> None:
    seeded = await _seed(session)
    session.add(
        CoverageReconciliation(
            reconciliation_id="crec_1",
            run_id=seeded["run"].run_id,
            source_id=seeded["source"].source_id,
            source_version_id=seeded["version"].source_version_id,
            jurisdiction_id="jur_ch_zh",
            attribution_status=CoverageAttributionStatus.ATTRIBUTED,
            denominator_tier=DenominatorTier.PUBLISHED,
            expected=1377,
            observed=1377,
            truncated=True,
            as_of=_NOW,
        )
    )
    await session.flush()

    payload = await CoverageService(session).get_acquisition_coverage()
    entry = next(e for e in payload["data"] if e["jurisdiction_id"] == "jur_ch_zh")
    assert entry["expected"] == 1377
    assert entry["denominator_truncated"] is True
    assert entry["acquired_gap"] is None


@pytest.mark.asyncio
async def test_unattributed_reconciliation_is_summarised_not_shown_per_jurisdiction(
    session: AsyncSession,
) -> None:
    seeded = await _seed(session)
    session.add(
        CoverageReconciliation(
            reconciliation_id="crec_amb",
            run_id=seeded["run"].run_id,
            source_id=seeded["source"].source_id,
            source_version_id=seeded["version"].source_version_id,
            jurisdiction_id=None,
            attribution_status=CoverageAttributionStatus.AMBIGUOUS_MULTI_ENTITY,
            denominator_tier=DenominatorTier.PUBLISHED,
            expected=None,
            observed=2498,
            as_of=_NOW,
        )
    )
    await session.flush()

    payload = await CoverageService(session).get_acquisition_coverage()
    assert payload["summary"]["reconciliations_unattributed"] == 1
    entry = next(e for e in payload["data"] if e["jurisdiction_id"] == "jur_ch_zh")
    assert entry["expected"] is None


@pytest.mark.asyncio
async def test_newest_reconciliation_wins_and_the_competition_is_visible(
    session: AsyncSession,
) -> None:
    """Two sources measuring one canton must not silently overwrite each other."""
    seeded = await _seed(session)
    for idx, (as_of, expected) in enumerate(((_NOW - timedelta(days=1), 1300), (_NOW, 1377))):
        session.add(
            CoverageReconciliation(
                reconciliation_id=f"crec_{idx}",
                run_id=seeded["run"].run_id,
                source_id=seeded["source"].source_id,
                source_version_id=seeded["version"].source_version_id,
                jurisdiction_id="jur_ch_zh",
                attribution_status=CoverageAttributionStatus.ATTRIBUTED,
                denominator_tier=DenominatorTier.PUBLISHED,
                expected=expected,
                observed=expected,
                as_of=as_of,
            )
        )
    await session.flush()

    payload = await CoverageService(session).get_acquisition_coverage()
    entry = next(e for e in payload["data"] if e["jurisdiction_id"] == "jur_ch_zh")
    assert entry["expected"] == 1377
    assert entry["reconciliation_count"] == 2


@pytest.mark.asyncio
async def test_reconciliation_survives_a_source_rejurisdiction(session: AsyncSession) -> None:
    """The persist-vs-compute argument, executable.

    Attribution is captured with the measurement. Re-pointing the source afterwards must
    not retroactively move Zürich's published total to another canton — which is exactly
    what computing the ledger on demand from `provider_jobs.response_payload` would do.
    """
    seeded = await _seed(session)
    await _seed(session, jurisdiction_id="jur_ch_be")
    session.add(
        CoverageReconciliation(
            reconciliation_id="crec_stable",
            run_id=seeded["run"].run_id,
            source_id=seeded["source"].source_id,
            source_version_id=seeded["version"].source_version_id,
            jurisdiction_id="jur_ch_zh",
            attribution_status=CoverageAttributionStatus.ATTRIBUTED,
            denominator_tier=DenominatorTier.PUBLISHED,
            expected=1377,
            observed=1377,
            as_of=_NOW,
        )
    )
    await session.flush()

    seeded["source"].jurisdiction_id = "jur_ch_be"
    await session.flush()

    payload = await CoverageService(session).get_acquisition_coverage()
    zh = next(e for e in payload["data"] if e["jurisdiction_id"] == "jur_ch_zh")
    be = next(e for e in payload["data"] if e["jurisdiction_id"] == "jur_ch_be")
    assert zh["expected"] == 1377
    assert be["expected"] is None


@pytest.mark.asyncio
async def test_summary_names_the_stage_it_cannot_measure(session: AsyncSession) -> None:
    await _seed(session)
    payload = await CoverageService(session).get_acquisition_coverage()
    assert payload["summary"]["unmeasured_stages"] == ["indexed"]
    assert payload["basis"] == "platform_control_runs"


@pytest.mark.asyncio
async def test_empty_ledger_reports_its_horizon_rather_than_looking_broken(
    session: AsyncSession,
) -> None:
    """No reconciliations yet is the honest day-one state, not an empty answer."""
    await _seed(session)
    payload = await CoverageService(session).get_acquisition_coverage()
    assert payload["summary"]["reconciliations_recorded_since"] is None
    assert payload["summary"]["jurisdictions_with_published_denominator"] == 0
