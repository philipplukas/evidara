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

from platform_control.domain import DenominatorTier, NormLevel, RunMode


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
