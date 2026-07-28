"""One recorded answer to "how much of this jurisdiction does the source say exists?"

A row is written when an acquisition run reports a reconciliation — currently only the
LexFind digit-union enumeration (#816/#818), which reads the source's own published count
and compares it to what discovery found.

WHY THIS IS A TABLE AND NOT A QUERY
-----------------------------------
The same numbers already sit in ``provider_jobs.response_payload``. They are not read
from there, for four reasons, the last of which is disqualifying:

1. ``response_payload`` is a ``JSON`` column. Asking "which jobs carry coverage?" needs
   ``->>`` on Postgres and ``json_extract`` on SQLite, and this repo has already written
   down its position on dialect-specific SQL (``correction_service`` aggregates in Python
   after one bounded fetch, precisely to stay portable).
2. ``provider_jobs`` grows one row per run forever and a Firecrawl payload carries a whole
   crawl response. Deserializing all of them to find the handful with a ``coverage`` key
   is not an operator-facing read path.
3. **Attribution is a decision, not a stored fact.** The payload says ``entity_id: 26``,
   never ``jur_ch_zh``; the mapping runs through ``Source.jurisdiction_id`` at some
   moment in time. Re-pointing a source would retroactively re-attribute a measurement of
   Zürich's published total to a different canton. A row captured in the same transaction
   as the measurement cannot do that — and a test pins it.
4. Any bounded scan (``WHERE created_at >= now() - 90d``) makes "never measured" and
   "measured before the window" indistinguishable. That is ADR-0042's four-causes-of-an-
   empty-result failure rebuilt inside the endpoint meant to fix it, and there is no
   window that is both cheap and honest.

THE SECOND-PRODUCER RISK, AND HOW IT IS CLOSED
----------------------------------------------
A second home for a fact that already has one is how #675/#713 happened. Three
structural choices keep this from drifting rather than asking anyone to remember:

* the row is written in the **same transaction, from the same in-memory payload object**
  that becomes ``provider_jobs.response_payload`` — not from a re-read, not from a job;
* it stores **scalars plus a ``provider_job_id`` FK**, so it is a pointer to the evidence
  rather than a copy of it;
* ``test_persisted_row_agrees_with_the_provider_payload`` fails if they ever disagree.
"""

from __future__ import annotations

from datetime import datetime

from sqlalchemy import Boolean, DateTime, Enum, ForeignKey, Integer, String
from sqlalchemy.orm import Mapped, mapped_column

from platform_control.domain import CoverageAttributionStatus, DenominatorTier, RunMode
from platform_control.ids import generate_prefixed_id
from platform_control.models.base import Base, TimestampMixin


class CoverageReconciliation(TimestampMixin, Base):
    __tablename__ = "coverage_reconciliations"

    reconciliation_id: Mapped[str] = mapped_column(
        primary_key=True, default=lambda: generate_prefixed_id("crec")
    )

    # Provenance. `provider_job_id` is the pointer back to the raw payload this row was
    # distilled from — without it the scalars below would be an unfalsifiable copy.
    run_id: Mapped[str] = mapped_column(ForeignKey("runs.run_id"), index=True)
    source_id: Mapped[str] = mapped_column(ForeignKey("sources.source_id"), index=True)
    source_version_id: Mapped[str] = mapped_column(ForeignKey("source_versions.source_version_id"))
    provider_job_id: Mapped[str | None] = mapped_column(
        ForeignKey("provider_jobs.provider_job_id"), nullable=True
    )

    # NULLABLE on purpose. A run covering several entities cannot be attributed to the
    # one jurisdiction its source names, and inventing a split would be worse than
    # admitting the gap. Following `Run.refused`, the row is still written so the attempt
    # leaves evidence rather than silence.
    jurisdiction_id: Mapped[str | None] = mapped_column(
        ForeignKey("jurisdictions.jurisdiction_id"), nullable=True, index=True
    )
    attribution_status: Mapped[CoverageAttributionStatus] = mapped_column(
        Enum(
            CoverageAttributionStatus,
            native_enum=False,
            values_callable=lambda enum_cls: [member.value for member in enum_cls],
        ),
        default=CoverageAttributionStatus.ATTRIBUTED,
    )
    # The provider's own external key (LexFind 26 = ZH). Kept because it is what a future
    # entity -> jurisdiction mapping would need, and it is otherwise thrown away.
    entity_id: Mapped[str | None] = mapped_column(String, nullable=True)

    strategy: Mapped[str | None] = mapped_column(String, nullable=True)
    denominator_tier: Mapped[DenominatorTier] = mapped_column(
        Enum(
            DenominatorTier,
            native_enum=False,
            values_callable=lambda enum_cls: [member.value for member in enum_cls],
        ),
        default=DenominatorTier.NONE,
    )
    denominator_source: Mapped[str | None] = mapped_column(String, nullable=True)

    # NULL means "no denominator", never zero. `_positive_int_or_none` in the LexFind
    # provider enforces the same rule upstream, for the same reason: a source claiming to
    # publish no law at all is unstatable, and `observed == 0 == expected` would otherwise
    # read as complete coverage.
    expected: Mapped[int | None] = mapped_column(Integer, nullable=True)
    observed: Mapped[int] = mapped_column(Integer, default=0)

    # The provider's claim, recorded verbatim and never re-derived here. If the ledger
    # disagreed with it, that disagreement is a finding worth seeing.
    provider_complete_claim: Mapped[bool] = mapped_column(Boolean, default=False)
    # A capped run is a sample, not a measurement — gaps must be suppressed downstream.
    truncated: Mapped[bool] = mapped_column(Boolean, default=False)

    # Which mode produced the denominator. Preview and acceptance runs create real
    # captures, so they are counted; this is how an operator sees what produced a number.
    run_mode: Mapped[RunMode | None] = mapped_column(
        Enum(
            RunMode,
            native_enum=False,
            values_callable=lambda enum_cls: [member.value for member in enum_cls],
        ),
        nullable=True,
    )

    # When the EXTERNAL fact was read — not when this row was written. A denominator is a
    # point-in-time claim by the source; LexFind reports ~500 changes a month nationally.
    as_of: Mapped[datetime] = mapped_column(DateTime(timezone=True))
