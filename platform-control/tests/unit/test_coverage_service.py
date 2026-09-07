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
    CoverageWorkReason,
    DenominatorTier,
    NormLevel,
    ProcessingStatus,
    RunMode,
    RunStatus,
)
from platform_control.models.authority import Authority, Jurisdiction
from platform_control.models.captured_resource import CapturedResource
from platform_control.models.coverage_reconciliation import CoverageReconciliation
from platform_control.models.document_lifecycle_event import DocumentLifecycleEvent
from platform_control.models.processing_status_update import ProcessingStatusUpdate
from platform_control.models.run import Run
from platform_control.models.source import Source
from platform_control.models.source_version import SourceVersion
from platform_control.schemas.coverage import CoverageWorkQueueResponse
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


# ---------------------------------------------------------------------------
# Refusals in the ledger (#907)
# ---------------------------------------------------------------------------


def _quarantine(run_id: str, idx: int, *, document_id: str | None) -> ProcessingStatusUpdate:
    return ProcessingStatusUpdate(
        event_id=f"psu_{idx:026d}",
        run_id=run_id,
        processing_manifest_id=f"pm_{idx:026d}",
        processing_version="v1",
        status=ProcessingStatus.QUARANTINED,
        occurred_at=_NOW,
        document_id=document_id,
        error_code="adr_0047_quarantine",
        error_summary="withheld",
    )


async def _refused_run(session: AsyncSession, seeded: dict, run_id: str) -> Run:
    """A refusal record: terminal FAILED, marked in metadata, exactly as #634 writes it."""
    run = Run(
        run_id=run_id,
        source_id=seeded["source"].source_id,
        source_version_id=seeded["version"].source_version_id,
        mode=RunMode.ACCEPTANCE,
        status=RunStatus.FAILED,
        run_metadata={"refused": True, "reason": "blueprint_not_enabled"},
    )
    session.add(run)
    await session.flush()
    return run


@pytest.mark.asyncio
async def test_refused_runs_are_counted_and_never_netted_off_coverage(
    session: AsyncSession,
) -> None:
    """A refusal is a decision, not a hole to subtract.

    #634 made a blocked dispatch leave evidence instead of silence. Until this, that
    evidence was invisible per jurisdiction — the ledger could not answer "what did we
    decline to claim here?", which is half of #907's `expected / held / refused /
    unknown`.
    """
    seeded = await _seed(session)
    await _refused_run(session, seeded, "run_refused_1")
    await _refused_run(session, seeded, "run_refused_2")
    session.add(
        _captured(
            seeded["source"].source_id,
            seeded["run"].run_id,
            "https://example.test/a",
            1,
            version_id=seeded["version"].source_version_id,
        )
    )
    await session.flush()

    payload = await CoverageService(session).get_acquisition_coverage()
    entry = payload["data"][0]

    assert entry["refused_runs"] == 2
    # The held count is untouched: refusals are reported beside coverage, not inside it.
    assert entry["acquired_distinct_urls"] == 1


@pytest.mark.asyncio
async def test_a_failed_run_that_is_not_a_refusal_is_not_counted_as_one(
    session: AsyncSession,
) -> None:
    """The marker is the fact, not the status.

    Every refusal is FAILED; not every FAILED run is a refusal. Counting by status
    would report ordinary breakage as a deliberate decision — the exact conflation
    `Run.refused` exists to prevent.
    """
    seeded = await _seed(session)
    session.add(
        Run(
            run_id="run_just_broke",
            source_id=seeded["source"].source_id,
            source_version_id=seeded["version"].source_version_id,
            mode=RunMode.ACCEPTANCE,
            status=RunStatus.FAILED,
            run_metadata={"error": "timeout"},
        )
    )
    await session.flush()

    payload = await CoverageService(session).get_acquisition_coverage()
    assert payload["data"][0]["refused_runs"] == 0


@pytest.mark.asyncio
async def test_quarantined_documents_are_distinct_and_reported_per_jurisdiction(
    session: AsyncSession,
) -> None:
    seeded = await _seed(session)
    session.add(_quarantine(seeded["run"].run_id, 1, document_id="doc_a"))
    # Same document quarantined twice is one refused document, not two.
    session.add(_quarantine(seeded["run"].run_id, 2, document_id="doc_a"))
    session.add(_quarantine(seeded["run"].run_id, 3, document_id="doc_b"))
    await session.flush()

    payload = await CoverageService(session).get_acquisition_coverage()
    assert payload["data"][0]["quarantined_documents"] == 2


@pytest.mark.asyncio
async def test_unplaceable_quarantines_are_counted_not_dropped(session: AsyncSession) -> None:
    """`quarantined_documents == 0` must never be able to mean "we could not say where".

    Two causes, both counted: an event whose `run_id` matches no `Run`, and one that
    carries no `document_id` and so cannot be counted as a document at all. Dropping
    either would rebuild ADR-0042's four-causes-of-an-empty-result failure inside the
    field meant to expose refusals.
    """
    seeded = await _seed(session)
    session.add(_quarantine("run_that_does_not_exist", 1, document_id="doc_x"))
    session.add(_quarantine(seeded["run"].run_id, 2, document_id=None))
    await session.flush()

    payload = await CoverageService(session).get_acquisition_coverage()
    assert payload["data"][0]["quarantined_documents"] == 0
    assert payload["summary"]["quarantined_events_unattributable"] == 2


def _published_denominator(
    seeded: dict, *, reconciliation_id: str, expected: int
) -> CoverageReconciliation:
    """A PUBLISHED-tier denominator — the only tier that earns a gap."""
    return CoverageReconciliation(
        reconciliation_id=reconciliation_id,
        run_id=seeded["run"].run_id,
        source_id=seeded["source"].source_id,
        source_version_id=seeded["version"].source_version_id,
        jurisdiction_id="jur_ch_zh",
        attribution_status=CoverageAttributionStatus.ATTRIBUTED,
        denominator_tier=DenominatorTier.PUBLISHED,
        denominator_source="lexfind",
        expected=expected,
        observed=expected,
        truncated=False,
        run_mode=RunMode.ACCEPTANCE,
        as_of=_NOW,
    )


# ---------------------------------------------------------------------------
# The work queue (#907)
# ---------------------------------------------------------------------------


@pytest.mark.asyncio
async def test_a_jurisdiction_with_no_denominator_leads_the_queue(session: AsyncSession) -> None:
    """`no_denominator` is the reason that makes every other answer unstatable.

    It is also the largest category by far, and the one a source-keyed queue would
    have made invisible — a jurisdiction with no denominator usually has no source
    either, which is exactly why the queue is keyed on jurisdictions.
    """
    await _seed(session)
    payload = await CoverageService(session).get_coverage_work_queue()

    item = payload["data"][0]
    assert CoverageWorkReason.NO_DENOMINATOR in item["reasons"]
    assert item["expected"] is None
    # An empty jurisdiction has never been acquired either — both are true, and the
    # queue reports both rather than picking one.
    assert CoverageWorkReason.NEVER_ACQUIRED in item["reasons"]


@pytest.mark.asyncio
async def test_the_queue_carries_no_score_and_says_how_it_is_ordered(
    session: AsyncSession,
) -> None:
    """ADR-0042 rejected a completeness percentage because every number needs a
    denominator. A priority score has the same defect, so there is not one — and the
    ordering rule travels in the payload so position is not read as priority."""
    await _seed(session)
    payload = await CoverageService(session).get_coverage_work_queue()

    assert payload["ordering"] == "reason_class_then_name"
    for item in payload["data"]:
        assert "score" not in item
        assert "priority" not in item
        assert "rank" not in item


@pytest.mark.asyncio
async def test_a_fully_covered_jurisdiction_is_absent_from_the_queue(
    session: AsyncSession,
) -> None:
    """Without this, every test above is satisfied by a queue that returns everything."""
    seeded = await _seed(session)
    session.add(_published_denominator(seeded, reconciliation_id="crec_q_covered", expected=1))
    session.add(
        _captured(
            seeded["source"].source_id,
            seeded["run"].run_id,
            "https://example.test/only",
            1,
            version_id=seeded["version"].source_version_id,
        )
    )
    session.add(_lifecycle(seeded["run"].run_id, "doc_1", 1, "document.processed"))
    await session.flush()

    payload = await CoverageService(session).get_coverage_work_queue()
    assert payload["data"] == []
    assert payload["total"] == 0


@pytest.mark.asyncio
async def test_holding_more_than_the_source_publishes_is_queued_as_a_finding(
    session: AsyncSession,
) -> None:
    """A negative gap is not "done".

    The schema already refuses to clamp one, because it means a dedup failure or a
    denominator counting something else. The queue has to agree: reporting it as
    complete would hide the very thing the negative gap was preserved to reveal.
    """
    seeded = await _seed(session)
    session.add(_published_denominator(seeded, reconciliation_id="crec_q_negative", expected=1))
    for idx, url in enumerate(("https://example.test/a", "https://example.test/b"), start=1):
        session.add(
            _captured(
                seeded["source"].source_id,
                seeded["run"].run_id,
                url,
                idx,
                version_id=seeded["version"].source_version_id,
            )
        )
    await session.flush()

    payload = await CoverageService(session).get_coverage_work_queue()
    reasons = payload["data"][0]["reasons"]
    assert CoverageWorkReason.HOLDINGS_EXCEED_DENOMINATOR in reasons
    assert payload["data"][0]["acquired_gap"] == -1


@pytest.mark.asyncio
async def test_refusals_put_a_jurisdiction_in_the_queue_on_their_own(
    session: AsyncSession,
) -> None:
    seeded = await _seed(session)
    await _refused_run(session, seeded, "run_refused_q")
    await session.flush()

    payload = await CoverageService(session).get_coverage_work_queue()
    assert CoverageWorkReason.REFUSALS_OUTSTANDING in payload["data"][0]["reasons"]
    assert payload["data"][0]["refused_runs"] == 1


@pytest.mark.asyncio
async def test_every_queued_reason_survives_the_schema_validators(
    session: AsyncSession,
) -> None:
    """The service and the schema must agree about what earns a reason.

    `CoverageWorkItem` refuses a reason whose supporting counts are absent — a label
    with no measurement behind it is the same defect as a percentage over an unknown
    denominator. Round-tripping through the model is what makes those validators load
    bearing rather than decorative.
    """
    seeded = await _seed(session)
    await _refused_run(session, seeded, "run_refused_v")
    await session.flush()

    payload = await CoverageService(session).get_coverage_work_queue()
    validated = CoverageWorkQueueResponse.model_validate(payload)
    assert validated.data
    assert all(item.reasons for item in validated.data)
