"""The acquisition-coverage read model — what a jurisdiction's funnel actually looks like.

    expected -> discovered -> acquired -> processed        [ indexed: NOT measured here ]

`indexed` is legal-search's half of the ADR-0042 §4 split and is deliberately absent:
platform-control has no OpenSearch dependency, so any number it reported would be an
inference dressed as a measurement. `unmeasured_stages` names the gap instead of hiding
it. (`run_service._resolve_search_stage` reports "searchable projection path is active"
from the bare existence of a lifecycle event — that is the anti-pattern this avoids.)

Aggregation runs in three grouped SELECTs assembled in Python, following
`correction_service`: plain `GROUP BY func.count` with no dialect-specific SQL, so the
same code runs on the SQLite test schema and production Postgres.
"""

from __future__ import annotations

from datetime import UTC, datetime
from typing import Any

from sqlalchemy import Select, distinct, func, select
from sqlalchemy.ext.asyncio import AsyncSession

from platform_control.domain import (
    CoverageAttributionStatus,
    CoverageWorkReason,
    DenominatorTier,
    ProcessingStatus,
    RunStatus,
)
from platform_control.models.authority import Jurisdiction
from platform_control.models.captured_resource import CapturedResource
from platform_control.models.coverage_reconciliation import CoverageReconciliation
from platform_control.models.document_lifecycle_event import DocumentLifecycleEvent
from platform_control.models.processing_status_update import ProcessingStatusUpdate
from platform_control.models.run import Run
from platform_control.models.source import Source

MAX_PAGE_SIZE = 500

# Pinned by `contracts/events/document-{processed,withdrawn}.schema.json`.
_PROCESSED_EVENT = "document.processed"
_WITHDRAWN_EVENT = "document.withdrawn"

# The stage this service structurally cannot see. Named, not omitted.
UNMEASURED_STAGES = ["indexed"]

# Queue ordering, most-blocking first. This is a stated convention, not a measurement:
# `no_denominator` sorts first because it is the one reason that makes every other
# answer unstatable, and a jurisdiction that has never been acquired is a bigger hole
# than one that is merely behind. The payload names the rule (`ordering`) so a caller
# reads position as "this convention" rather than as a priority score.
_WORK_REASON_ORDER = (
    CoverageWorkReason.NO_DENOMINATOR,
    CoverageWorkReason.NO_SOURCE,
    CoverageWorkReason.NEVER_ACQUIRED,
    CoverageWorkReason.HOLDINGS_EXCEED_DENOMINATOR,
    CoverageWorkReason.ACQUISITION_GAP,
    CoverageWorkReason.PROCESSING_GAP,
    CoverageWorkReason.REFUSALS_OUTSTANDING,
)


class CoverageService:
    def __init__(self, session: AsyncSession) -> None:
        self.session = session

    async def _scalar_map(self, statement: Select) -> dict[str, int]:
        rows = (await self.session.execute(statement)).all()
        return {row[0]: int(row[1] or 0) for row in rows if row[0] is not None}

    async def get_acquisition_coverage(
        self, *, limit: int | None = 100, offset: int = 0, level: str | None = None
    ) -> dict[str, Any]:
        """Report `expected -> discovered -> acquired -> processed` per jurisdiction.

        `limit=None` returns EVERY jurisdiction and is for internal callers only —
        the work queue, which cannot answer "which jurisdictions need work" from a
        page. It costs no extra database work: every aggregate below is already a
        whole-table `GROUP BY`, and only the jurisdiction list was ever paginated.
        The HTTP route never passes it.
        """
        # Clamp rather than reject, matching the reference-data endpoints (#666).
        if limit is not None:
            limit = max(1, min(limit, MAX_PAGE_SIZE))
        offset = max(0, offset)

        # --- acquired: two numbers in one pass -------------------------------------
        # DISTINCT final_url is the one gaps are computed from. COUNT(*) inflates across
        # re-runs — two full ZH sweeps give 2754 rows against expected 1377, driving the
        # gap negative for a reason that has nothing to do with coverage. `final_url` is
        # NOT NULL; `checksum` is nullable, so it cannot be the distinct key.
        acquired_rows = (
            await self.session.execute(
                select(
                    Source.jurisdiction_id,
                    func.count(CapturedResource.captured_resource_id),
                    func.count(distinct(CapturedResource.final_url)),
                )
                .join(Source, Source.source_id == CapturedResource.source_id)
                .group_by(Source.jurisdiction_id)
            )
        ).all()
        acquired_resources = {r[0]: int(r[1] or 0) for r in acquired_rows if r[0]}
        acquired_urls = {r[0]: int(r[2] or 0) for r in acquired_rows if r[0]}

        # --- processed / withdrawn --------------------------------------------------
        # DISTINCT document_id, not COUNT(*): a reprocess emits a second event for the
        # same document with a bumped revision, and counting events would report pipeline
        # activity as corpus size.
        processed = await self._scalar_map(self._lifecycle_statement(_PROCESSED_EVENT))
        withdrawn = await self._scalar_map(self._lifecycle_statement(_WITHDRAWN_EVENT))

        # Lifecycle events whose run_id matches no Run. `record_document_processed` never
        # validates the run exists, so an inner join silently eats these — and a document
        # we processed but cannot attribute is a finding, not a rounding error.
        unattributable = int(
            (
                await self.session.execute(
                    select(func.count(distinct(DocumentLifecycleEvent.document_id)))
                    .select_from(DocumentLifecycleEvent)
                    .outerjoin(Run, Run.run_id == DocumentLifecycleEvent.run_id)
                    .where(Run.run_id.is_(None))
                )
            ).scalar()
            or 0
        )

        # --- refusals ---------------------------------------------------------------
        refused_runs = await self._refused_runs_by_jurisdiction()
        quarantined, quarantine_unattributable = await self._quarantined_by_jurisdiction()

        # --- denominators -----------------------------------------------------------
        recs = (
            (
                await self.session.execute(
                    select(CoverageReconciliation).order_by(CoverageReconciliation.as_of.desc())
                )
            )
            .scalars()
            .all()
        )

        latest: dict[str, CoverageReconciliation] = {}
        counts: dict[str, int] = {}
        unattributed_total = 0
        earliest_recorded: datetime | None = None
        for rec in recs:
            if rec.created_at is not None and (
                earliest_recorded is None or rec.created_at < earliest_recorded
            ):
                earliest_recorded = rec.created_at
            if rec.attribution_status is CoverageAttributionStatus.ATTRIBUTED and (
                rec.jurisdiction_id
            ):
                counts[rec.jurisdiction_id] = counts.get(rec.jurisdiction_id, 0) + 1
                # Ordered by as_of DESC, so the first one seen wins.
                latest.setdefault(rec.jurisdiction_id, rec)
            else:
                unattributed_total += 1

        # --- jurisdictions ----------------------------------------------------------
        base = select(Jurisdiction)
        if level:
            base = base.where(Jurisdiction.level == level)
        total = int(
            (await self.session.execute(select(func.count()).select_from(base.subquery()))).scalar()
            or 0
        )
        paged = base.order_by(Jurisdiction.name.asc()).offset(offset)
        if limit is not None:
            paged = paged.limit(limit)
        page = (await self.session.execute(paged)).scalars().all()

        entries = [
            self._entry(
                jurisdiction,
                reconciliation=latest.get(jurisdiction.jurisdiction_id),
                reconciliation_count=counts.get(jurisdiction.jurisdiction_id, 0),
                acquired_resources=acquired_resources.get(jurisdiction.jurisdiction_id, 0),
                acquired_urls=acquired_urls.get(jurisdiction.jurisdiction_id, 0),
                processed=processed.get(jurisdiction.jurisdiction_id, 0),
                withdrawn=withdrawn.get(jurisdiction.jurisdiction_id, 0),
                refused_runs=refused_runs.get(jurisdiction.jurisdiction_id, 0),
                quarantined_documents=quarantined.get(jurisdiction.jurisdiction_id, 0),
            )
            for jurisdiction in page
        ]

        return {
            "basis": "platform_control_runs",
            "as_of": datetime.now(UTC),
            "data": entries,
            "total": total,
            "limit": limit,
            "offset": offset,
            "summary": {
                "jurisdictions_total": total,
                "jurisdictions_with_any_acquired": len(
                    [j for j, n in acquired_urls.items() if n > 0]
                ),
                "jurisdictions_with_any_processed": len([j for j, n in processed.items() if n > 0]),
                "jurisdictions_with_published_denominator": len(
                    [
                        j
                        for j, r in latest.items()
                        if r.denominator_tier is DenominatorTier.PUBLISHED
                    ]
                ),
                "jurisdictions_with_registry_denominator": len(
                    [j for j, r in latest.items() if r.denominator_tier is DenominatorTier.REGISTRY]
                ),
                "reconciliations_unattributed": unattributed_total,
                "processed_documents_unattributable": unattributable,
                "quarantined_events_unattributable": quarantine_unattributable,
                # The ledger's own horizon. Without it an empty table reads as "we
                # measured and found nothing" rather than "nothing has been measured yet".
                "reconciliations_recorded_since": earliest_recorded,
                "unmeasured_stages": list(UNMEASURED_STAGES),
            },
        }

    async def get_coverage_work_queue(self, *, limit: int = 50) -> dict[str, Any]:
        """The jurisdictions that need work, and why — #907's queue read.

        Built on top of the ledger rather than beside it. Deriving the same counts a
        second way is how a second producer starts, and this repo has paid for that
        twice already (#675, #713); a queue that disagreed with the ledger it is a view
        of would be worse than no queue.

        NO SCORE, and no single "primary" reason. Ordering is by reason class then name
        — stated in the payload as `ordering` so a caller never reads position as
        priority — and every reason true of a jurisdiction travels with it. A priority
        number needs a denominator exactly as much as a completeness percentage does,
        and this read has no basis for one (ADR-0042).
        """
        limit = max(1, min(limit, MAX_PAGE_SIZE))

        # EVERY jurisdiction, not one page.
        #
        # This used to read `limit=MAX_PAGE_SIZE`, which meant the queue was computed
        # over the first 500 jurisdictions alphabetically and reported the other 1,669
        # as `unqueued_unmeasurable`. It was honest — it never claimed completeness —
        # but a worklist that cannot see 77% of the estate is not a worklist (#928).
        # It costs no extra scans: the ledger's aggregates are already whole-table.
        ledger = await self.get_acquisition_coverage(limit=None, offset=0)
        entries: list[dict[str, Any]] = ledger["data"]

        # Kept, and now structurally zero. A jurisdiction the ledger could not include
        # would still be one we cannot speak about, so the field stays rather than
        # being deleted as "always 0" — the day it is not, it must say so.
        unqueued = max(0, int(ledger.get("total") or 0) - len(entries))

        source_ids: dict[str, list[str]] = {}
        for jurisdiction_id, source_id in (
            await self.session.execute(
                select(Source.jurisdiction_id, Source.source_id).order_by(Source.source_id.asc())
            )
        ).all():
            if jurisdiction_id:
                source_ids.setdefault(jurisdiction_id, []).append(source_id)

        items: list[dict[str, Any]] = []
        without_a_source = 0
        for entry in entries:
            sources = source_ids.get(entry["jurisdiction_id"], [])
            reasons = self._work_reasons(entry, has_source=bool(sources))
            if not reasons:
                continue
            # A jurisdiction with no source is REPORTED AS A COUNT, not as a row.
            #
            # Measured 2026-09-07: 5 of 2,169 jurisdictions have any source, so
            # listing the rest produced 2,164 identical rows that buried the five
            # real ones — the same alphabetical wall the ledger already had. The work
            # they imply is "register a source", which is a repo edit and a deploy
            # (#736) and none of this queue's actions.
            #
            # Counted rather than dropped: `jurisdictions_without_a_source` is the
            # honest form of the same fact, and a caller that wants the list has the
            # ledger.
            if CoverageWorkReason.NO_SOURCE in reasons:
                without_a_source += 1
                continue
            items.append(
                {
                    "jurisdiction_id": entry["jurisdiction_id"],
                    "name": entry["name"],
                    "slug": entry["slug"],
                    "level": entry["level"],
                    "reasons": reasons,
                    "expected": entry["expected"],
                    "denominator_tier": entry["denominator_tier"],
                    "acquired_distinct_urls": entry["acquired_distinct_urls"],
                    "processed_documents": entry["processed_documents"],
                    "acquired_gap": entry["acquired_gap"],
                    "processed_gap": entry["processed_gap"],
                    "refused_runs": entry["refused_runs"],
                    "quarantined_documents": entry["quarantined_documents"],
                    "source_ids": sources,
                }
            )

        rank = {reason: index for index, reason in enumerate(_WORK_REASON_ORDER)}
        items.sort(key=lambda item: (min(rank[r] for r in item["reasons"]), item["name"]))

        return {
            "basis": "platform_control_runs",
            "as_of": datetime.now(UTC),
            "ordering": "reason_class_then_name",
            "unqueued_unmeasurable": unqueued,
            "jurisdictions_without_a_source": without_a_source,
            "data": items[:limit],
            "total": len(items),
            "limit": limit,
        }

    @staticmethod
    def _work_reasons(entry: dict[str, Any], *, has_source: bool) -> list[CoverageWorkReason]:
        """Every reason true of one ledger entry.

        Each test mirrors a validator on `CoverageWorkItem`, so a reason that this
        method emits without the counts to support it fails at serialisation rather
        than reaching a caller as an unbacked label.
        """
        if not has_source:
            # Short-circuit on purpose. A sourceless jurisdiction trivially also has
            # no denominator and has never been acquired, and emitting all three
            # would make it look like three problems when it is one.
            return [CoverageWorkReason.NO_SOURCE]

        reasons: list[CoverageWorkReason] = []
        acquired_gap = entry["acquired_gap"]
        processed_gap = entry["processed_gap"]

        if entry["expected"] is None:
            reasons.append(CoverageWorkReason.NO_DENOMINATOR)
        if entry["acquired_distinct_urls"] == 0:
            reasons.append(CoverageWorkReason.NEVER_ACQUIRED)
        if acquired_gap is not None and acquired_gap > 0:
            reasons.append(CoverageWorkReason.ACQUISITION_GAP)
        if processed_gap is not None and processed_gap > 0:
            reasons.append(CoverageWorkReason.PROCESSING_GAP)
        if (acquired_gap is not None and acquired_gap < 0) or (
            processed_gap is not None and processed_gap < 0
        ):
            reasons.append(CoverageWorkReason.HOLDINGS_EXCEED_DENOMINATOR)
        if entry["refused_runs"] > 0:
            reasons.append(CoverageWorkReason.REFUSALS_OUTSTANDING)
        return reasons

    async def _refused_runs_by_jurisdiction(self) -> dict[str, int]:
        """Count runs that are refusal records, per jurisdiction.

        `Run.refused` reads `run_metadata["refused"]`, and `run_metadata` is a JSON
        column. Filtering it in SQL needs `->>` on Postgres and `json_extract` on
        SQLite, and this module's own docstring already states the position on
        dialect-specific SQL: aggregate in Python after one narrow fetch, so the same
        code runs on the SQLite test schema and production Postgres.

        The fetch is narrowed to FAILED runs because that is the only status
        `_record_refused_run` writes. It is deliberately NOT narrowed by time: a
        `WHERE created_at >= now() - 90d` would make "never refused" and "refused
        before the window" indistinguishable, which is the failure
        `coverage_reconciliation`'s docstring calls disqualifying.
        """
        rows = (
            await self.session.execute(
                select(Source.jurisdiction_id, Run.run_metadata)
                .join(Source, Source.source_id == Run.source_id)
                .where(Run.status == RunStatus.FAILED)
            )
        ).all()

        counts: dict[str, int] = {}
        for jurisdiction_id, metadata in rows:
            if not jurisdiction_id:
                continue
            if (metadata or {}).get("refused") is True:
                counts[jurisdiction_id] = counts.get(jurisdiction_id, 0) + 1
        return counts

    async def _quarantined_by_jurisdiction(self) -> tuple[dict[str, int], int]:
        """Distinct quarantined documents per jurisdiction, and what could not be placed.

        Returns `(counts, unattributable)`. A quarantine event is unattributable when
        its `run_id` matches no `Run`, or when it carries no `document_id` and so
        cannot be counted as a document at all. Both are counted rather than dropped:
        `quarantined_documents == 0` must not be able to mean "we could not say where".

        DISTINCT `document_id`, not `COUNT(*)`, for the same reason the lifecycle
        counts use it — a document quarantined twice is one refused document, not two.
        """
        attributed = (
            await self.session.execute(
                select(
                    Source.jurisdiction_id,
                    func.count(distinct(ProcessingStatusUpdate.document_id)),
                )
                .join(Run, Run.run_id == ProcessingStatusUpdate.run_id)
                .join(Source, Source.source_id == Run.source_id)
                .where(
                    ProcessingStatusUpdate.status == ProcessingStatus.QUARANTINED,
                    ProcessingStatusUpdate.document_id.is_not(None),
                )
                .group_by(Source.jurisdiction_id)
            )
        ).all()

        orphaned = int(
            (
                await self.session.execute(
                    select(func.count())
                    .select_from(ProcessingStatusUpdate)
                    .outerjoin(Run, Run.run_id == ProcessingStatusUpdate.run_id)
                    .where(
                        ProcessingStatusUpdate.status == ProcessingStatus.QUARANTINED,
                        Run.run_id.is_(None),
                    )
                )
            ).scalar()
            or 0
        )
        documentless = int(
            (
                await self.session.execute(
                    select(func.count())
                    .select_from(ProcessingStatusUpdate)
                    .outerjoin(Run, Run.run_id == ProcessingStatusUpdate.run_id)
                    .where(
                        ProcessingStatusUpdate.status == ProcessingStatus.QUARANTINED,
                        ProcessingStatusUpdate.document_id.is_(None),
                        Run.run_id.is_not(None),
                    )
                )
            ).scalar()
            or 0
        )

        counts = {row[0]: int(row[1] or 0) for row in attributed if row[0]}
        return counts, orphaned + documentless

    @staticmethod
    def _lifecycle_statement(event_type: str) -> Select:
        return (
            select(
                Source.jurisdiction_id,
                func.count(distinct(DocumentLifecycleEvent.document_id)),
            )
            .join(Run, Run.run_id == DocumentLifecycleEvent.run_id)
            .join(Source, Source.source_id == Run.source_id)
            .where(DocumentLifecycleEvent.event_type == event_type)
            .group_by(Source.jurisdiction_id)
        )

    @staticmethod
    def _entry(
        jurisdiction: Jurisdiction,
        *,
        reconciliation: CoverageReconciliation | None,
        reconciliation_count: int,
        acquired_resources: int,
        acquired_urls: int,
        processed: int,
        withdrawn: int,
        refused_runs: int = 0,
        quarantined_documents: int = 0,
    ) -> dict[str, Any]:
        tier = reconciliation.denominator_tier if reconciliation else DenominatorTier.NONE
        expected = reconciliation.expected if reconciliation else None
        truncated = bool(reconciliation.truncated) if reconciliation else False

        # A gap is only meaningful when the denominator counts the same things the
        # numerator does, and when the run was a measurement rather than a sample.
        #   - PUBLISHED counts texts of law, comparable to captured documents.
        #   - REGISTRY counts UNITS (2110 communes). Subtracting documents from units
        #     yields a number in no unit at all, so it is suppressed entirely.
        #   - truncated runs are samples.
        gaps_are_meaningful = (
            expected is not None and tier is DenominatorTier.PUBLISHED and not truncated
        )

        return {
            "jurisdiction_id": jurisdiction.jurisdiction_id,
            "name": jurisdiction.name,
            "slug": jurisdiction.slug,
            "level": jurisdiction.level,
            "expected": expected,
            "denominator_tier": tier,
            "denominator_source": reconciliation.denominator_source if reconciliation else None,
            "denominator_as_of": reconciliation.as_of if reconciliation else None,
            "denominator_run_id": reconciliation.run_id if reconciliation else None,
            "denominator_run_mode": reconciliation.run_mode if reconciliation else None,
            "denominator_truncated": truncated,
            "provider_complete_claim": (
                reconciliation.provider_complete_claim if reconciliation else None
            ),
            # Surfaced so two sources competing over one jurisdiction is visible rather
            # than silently resolved by "latest wins".
            "reconciliation_count": reconciliation_count,
            "discovered": reconciliation.observed if reconciliation else None,
            "acquired_resources": acquired_resources,
            "acquired_distinct_urls": acquired_urls,
            "processed_documents": processed,
            "withdrawn_documents": withdrawn,
            "refused_runs": refused_runs,
            "quarantined_documents": quarantined_documents,
            "acquired_gap": (expected - acquired_urls) if gaps_are_meaningful else None,
            "processed_gap": (expected - processed) if gaps_are_meaningful else None,
        }
