"""Acquisition-coverage shapes, and the rules that stop them lying.

ADR-0042 rejected a coverage percentage **outright**: *"Every such number needs a
denominator … A completeness score would be the single most dangerous field we could ship
here."* Nothing in this module emits a percentage, ratio or score — raw counts and gaps
only, so an operator reads `1377 / 1377` and draws their own conclusion.
`test_coverage_never_publishes_a_completeness_score` enforces that against the generated
contract rather than asking anyone to remember it.

The validators below are the honesty rules. Each has exactly one test.
"""

from __future__ import annotations

from datetime import datetime

from pydantic import BaseModel, Field, model_validator

from platform_control.domain import (
    CoverageWorkAction,
    CoverageWorkActor,
    CoverageWorkReason,
    DenominatorTier,
    NormLevel,
    RunMode,
)


class AcquisitionCoverageEntry(BaseModel):
    jurisdiction_id: str
    name: str
    slug: str
    level: NormLevel

    # NULL means "no denominator". Never 0 — a source that publishes nothing is
    # unstatable, and rendering it as zero would make `observed == 0` read as complete.
    expected: int | None = None
    denominator_tier: DenominatorTier = DenominatorTier.NONE
    denominator_source: str | None = None
    denominator_as_of: datetime | None = None
    denominator_run_id: str | None = None
    denominator_run_mode: RunMode | None = None
    denominator_truncated: bool = False
    provider_complete_claim: bool | None = None
    reconciliation_count: int = Field(default=0, ge=0)

    discovered: int | None = Field(default=None, ge=0)
    acquired_resources: int = Field(default=0, ge=0)
    acquired_distinct_urls: int = Field(default=0, ge=0)
    processed_documents: int = Field(default=0, ge=0)
    withdrawn_documents: int = Field(default=0, ge=0)

    # What this jurisdiction was NOT willing to claim, kept beside what it holds.
    #
    # Deliberately two fields in two units, never one total. A refused RUN and a
    # quarantined DOCUMENT are different things, and this module already refuses to
    # subtract a unit count from a document count (`_gaps_must_be_earned`). Summing
    # them would produce exactly the number-in-no-unit that rule exists to prevent.
    #
    # Neither is subtracted from anything either. A refusal is not a hole in coverage
    # to be netted off — it is a decision the platform made and can be asked about.
    # #634 made refusals leave evidence rather than silence; this is where that
    # evidence becomes countable per jurisdiction.
    refused_runs: int = Field(default=0, ge=0)
    quarantined_documents: int = Field(default=0, ge=0)

    # Deliberately NOT `ge=0`. A negative gap means we hold more than the source claims to
    # publish — a dedup failure or a denominator counting something else. That is a
    # finding worth surfacing, and clamping it away would hide the very thing this
    # endpoint exists to reveal.
    acquired_gap: int | None = None
    processed_gap: int | None = None

    @model_validator(mode="after")
    def _gaps_must_be_earned(self) -> AcquisitionCoverageEntry:
        if self.expected is None:
            if self.denominator_tier is not DenominatorTier.NONE:
                raise ValueError(
                    "expected is None, so denominator_tier must be 'none' — a tier that "
                    "promises a denominator without carrying one is the claim this "
                    "endpoint exists to prevent"
                )
            if self.acquired_gap is not None or self.processed_gap is not None:
                raise ValueError("a gap without a denominator is invented; both gaps must be None")
        elif self.denominator_tier is DenominatorTier.NONE:
            raise ValueError("denominator_tier 'none' cannot carry an expected count")

        if self.denominator_tier is DenominatorTier.REGISTRY and (
            self.acquired_gap is not None or self.processed_gap is not None
        ):
            # `expected` counts UNITS (2110 communes); the numerators count documents.
            # Subtracting them yields a number in no unit at all that reads as coverage.
            raise ValueError(
                "a registry-tier denominator counts units, not documents — it may not produce a gap"
            )

        if self.denominator_truncated:
            if self.acquired_gap is not None or self.processed_gap is not None:
                raise ValueError(
                    "a truncated run is a sample, not a measurement; gaps must be None"
                )
            if self.provider_complete_claim is True:
                raise ValueError("a truncated run cannot claim completeness")
        return self


class AcquisitionCoverageSummary(BaseModel):
    jurisdictions_total: int = Field(ge=0)
    jurisdictions_with_any_acquired: int = Field(ge=0)
    jurisdictions_with_any_processed: int = Field(ge=0)
    jurisdictions_with_published_denominator: int = Field(ge=0)
    jurisdictions_with_registry_denominator: int = Field(ge=0)
    reconciliations_unattributed: int = Field(ge=0)
    processed_documents_unattributable: int = Field(ge=0)
    # Quarantine events that could not be attributed to a jurisdiction, for either of
    # two reasons: the event's `run_id` matches no `Run`, or it carries no
    # `document_id` and so cannot be counted as a document. Both are counted here
    # rather than dropped — a refusal we cannot place is a finding, and silently
    # excluding it would make `quarantined_documents == 0` read as "nothing was
    # refused" when it means "we could not say where".
    quarantined_events_unattributable: int = Field(default=0, ge=0)
    # The ledger's own horizon — None until the first reconciliation is recorded. Named
    # the way ADR-0042 names `last_processed_at`: exactly as strong as the field name.
    reconciliations_recorded_since: datetime | None = None
    # Stages this service structurally cannot observe. `indexed` lives in legal-search
    # (`GET /v1/coverage`), which is the other half of the ADR-0042 §4 split.
    unmeasured_stages: list[str] = Field(default_factory=list)


class AcquisitionCoverageListResponse(BaseModel):
    # Mirrors ADR-0042's `basis: "index"`: a reader must be able to tell which side of
    # the split answered, because the two answer different questions.
    basis: str = "platform_control_runs"
    as_of: datetime
    summary: AcquisitionCoverageSummary
    data: list[AcquisitionCoverageEntry]
    total: int | None = None
    limit: int | None = None
    offset: int | None = None


class CoverageWorkItem(BaseModel):
    """One jurisdiction that needs work, and why.

    The unit is a JURISDICTION, not a source, even though #907 phrases the queue as
    "the next N sources". That is deliberate: the denominator this queue reasons about
    is stated per jurisdiction, and the most common reason to appear here —
    `no_denominator` — is true of jurisdictions that have no source at all. Keying on
    sources would make the largest category of work invisible, which is the exact
    failure the ledger exists to prevent.

    `sources` names what already exists to act through, and is empty precisely when the
    action is "create one".
    """

    jurisdiction_id: str
    name: str
    slug: str
    level: NormLevel

    # Every reason that is true of this jurisdiction, not the "main" one. Picking one
    # would be a ranking, and a ranking is the score this module does not ship.
    reasons: list[CoverageWorkReason] = Field(min_length=1)

    # The counts the reasons are read from, so a caller never has to trust the labels.
    # Same nullability contract as the ledger: `expected` is None for "unknown", never 0.
    expected: int | None = None
    denominator_tier: DenominatorTier = DenominatorTier.NONE
    acquired_distinct_urls: int = Field(default=0, ge=0)
    processed_documents: int = Field(default=0, ge=0)
    acquired_gap: int | None = None
    processed_gap: int | None = None
    refused_runs: int = Field(default=0, ge=0)
    quarantined_documents: int = Field(default=0, ge=0)

    source_ids: list[str] = Field(default_factory=list)

    # What to do, and who may do it. Derived from `reasons` server-side so every
    # client reads one answer (ADR-0056 constraint 1). Before #964 this mapping
    # existed only in `tools/evidara-cli`'s `agent_loop.py`, and a second client
    # deriving it from the queue's own sort order got `refusals_outstanding` +
    # `never_acquired` — the normal shape of a refusal — classified as work the
    # agent may do.
    #
    # This does NOT reintroduce the ranking `CoverageWorkReason` refuses to ship:
    # `reasons` is still the unranked truth and the counts still travel with it.
    # `proposed_action` names the most constraining response; `actor` is folded over
    # every reason, so it does not depend on which one is named.
    proposed_action: CoverageWorkAction
    actor: CoverageWorkActor

    @model_validator(mode="after")
    def _reasons_must_be_earned(self) -> CoverageWorkItem:
        """Every reason must be supported by the counts travelling with it.

        Without this the queue could assert `acquisition_gap` beside a null gap — a
        label with no measurement behind it, which is the same defect as a percentage
        over an unknown denominator.
        """
        if CoverageWorkReason.NO_DENOMINATOR in self.reasons and self.expected is not None:
            raise ValueError("no_denominator cannot be claimed when expected is known")
        if CoverageWorkReason.NEVER_ACQUIRED in self.reasons and self.acquired_distinct_urls > 0:
            raise ValueError("never_acquired cannot be claimed when something was acquired")
        if CoverageWorkReason.ACQUISITION_GAP in self.reasons and not (
            self.acquired_gap is not None and self.acquired_gap > 0
        ):
            raise ValueError("acquisition_gap requires a positive acquired_gap")
        if CoverageWorkReason.PROCESSING_GAP in self.reasons and not (
            self.processed_gap is not None and self.processed_gap > 0
        ):
            raise ValueError("processing_gap requires a positive processed_gap")
        if CoverageWorkReason.HOLDINGS_EXCEED_DENOMINATOR in self.reasons and not (
            (self.acquired_gap is not None and self.acquired_gap < 0)
            or (self.processed_gap is not None and self.processed_gap < 0)
        ):
            raise ValueError("holdings_exceed_denominator requires a negative gap")
        if CoverageWorkReason.REFUSALS_OUTSTANDING in self.reasons and self.refused_runs == 0:
            raise ValueError("refusals_outstanding requires at least one refused run")
        return self


class CoverageWorkQueueResponse(BaseModel):
    basis: str = "platform_control_runs"
    as_of: datetime

    # How the list is ordered, stated in the payload so position is never mistaken for
    # priority. There is no score field and there will not be one: a priority number
    # needs a denominator exactly as much as a completeness percentage does
    # (ADR-0042), and this queue has no basis for one.
    ordering: str = "reason_class_then_name"

    # Jurisdictions this read structurally cannot place in the queue. A jurisdiction
    # excluded for an unknown cause must not silently look like a jurisdiction with no
    # work — that is ADR-0042's four-causes-of-an-empty-result failure again.
    #
    # Structurally zero since #928 (the queue reads the whole estate), and kept for
    # exactly that reason: the day it is not zero, it has to be able to say so.
    unqueued_unmeasurable: int = Field(default=0, ge=0)

    # Jurisdictions with no source at all, reported as a count rather than as rows.
    #
    # Not a way of hiding them. 5 of 2,169 jurisdictions have a source (measured
    # 2026-09-07), so listing the rest returned 2,164 identical rows that buried the
    # five real ones. The work they imply — registering a source — is a repo edit and
    # a deploy (#736), which none of this queue's actions can express. A caller that
    # wants the list reads the ledger; a caller that wants the fact reads this.
    jurisdictions_without_a_source: int = Field(default=0, ge=0)

    data: list[CoverageWorkItem]
    total: int | None = None
    limit: int | None = None
