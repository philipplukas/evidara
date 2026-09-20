from __future__ import annotations

from datetime import datetime
from typing import Any

from pydantic import BaseModel, ConfigDict, Field, HttpUrl, model_validator

from platform_control.domain import (
    PipelineStageStatus,
    ProcessingReconciliationVerdict,
    ProcessingStatus,
    ProviderJobStatus,
    RunMode,
    RunRefusalCode,
    RunReplayMode,
    RunScopeKind,
    RunStatus,
)


class RunScopeRequest(BaseModel):
    kind: RunScopeKind = RunScopeKind.FULL_SOURCE
    source_snapshot_id: str | None = Field(default=None, pattern=r"^snap_[a-z0-9]+$")
    captured_resource_ids: list[str] = Field(default_factory=list)
    include_urls: list[HttpUrl] = Field(default_factory=list)
    since: datetime | None = None
    until: datetime | None = None
    max_resources: int | None = Field(default=None, ge=1, le=10000)

    model_config = ConfigDict(extra="forbid")

    @model_validator(mode="after")
    def validate_scope(self) -> RunScopeRequest:
        if self.kind is RunScopeKind.FULL_SOURCE:
            if any(
                [
                    self.source_snapshot_id,
                    self.captured_resource_ids,
                    self.include_urls,
                    self.since,
                    self.until,
                    self.max_resources,
                ]
            ):
                raise ValueError("full_source scope cannot include narrowing fields")
        elif self.kind is RunScopeKind.SOURCE_SNAPSHOT:
            if not self.source_snapshot_id:
                raise ValueError("source_snapshot scope requires source_snapshot_id")
        elif self.kind is RunScopeKind.DISCOVERED_SUBSET:
            if not (
                self.captured_resource_ids or self.include_urls or self.max_resources is not None
            ):
                raise ValueError(
                    "discovered_subset scope requires captured_resource_ids, "
                    "include_urls, or max_resources"
                )
        elif self.kind is RunScopeKind.TIME_WINDOW:
            if not (self.since or self.until):
                raise ValueError("time_window scope requires since or until")

        if self.since and self.until and self.since > self.until:
            raise ValueError("scope since must be earlier than or equal to until")
        return self


class RunReplayRequest(BaseModel):
    mode: RunReplayMode
    parent_run_id: str | None = Field(default=None, pattern=r"^run_[a-z0-9]+$")
    reason: str | None = None

    model_config = ConfigDict(extra="forbid")

    @model_validator(mode="after")
    def validate_replay(self) -> RunReplayRequest:
        if self.mode in {RunReplayMode.PARTIAL_RERUN, RunReplayMode.FULL_REFRESH}:
            if not self.parent_run_id:
                raise ValueError(f"{self.mode.value} replay requires parent_run_id")
        return self


class CreateRunRequest(BaseModel):
    source_id: str
    source_version_id: str
    mode: RunMode = RunMode.PREVIEW
    scope: RunScopeRequest = Field(default_factory=RunScopeRequest)
    replay: RunReplayRequest | None = None

    model_config = ConfigDict(extra="forbid")


class RunResponse(BaseModel):
    run_id: str = Field(examples=["run_01hzxk9c4dnpf8h6t2m5q7w3"])
    source_id: str
    source_version_id: str
    mode: RunMode
    scope: RunScopeRequest
    replay: RunReplayRequest | None
    replay_checkpoint: dict[str, Any] | None = None
    status: RunStatus
    started_at: datetime | None
    completed_at: datetime | None
    artifacts_count: int
    captured_resources_count: int
    failure_reason: str | None
    refused: bool = Field(
        default=False,
        description=(
            "True when the ADR-0030 two-key lock blocked this dispatch. The run is a "
            "refusal record — terminal FAILED, never dispatched — kept so an operator can "
            "ask what was attempted and why it was refused (#634)."
        ),
    )
    refusal_code: RunRefusalCode | None = Field(
        default=None,
        description=(
            "Why the dispatch was refused, as a code rather than a sentence (#908). "
            "`None` for a run that was not refused, and also for refusals recorded "
            "before this field existed — an absent code means 'not classified', never "
            "'not refused'; read `refused` for that. `failure_reason` keeps the prose, "
            "which is the part naming WHICH template or policy. Same shape as the "
            "ADR-0030 enablement guard's `refusals[].code` (#854), so both refusal "
            "surfaces branch the same way."
        ),
    )
    published_artifacts_count: int = Field(
        default=0,
        description=(
            "How many of `artifacts_count` actually reached the broker. Equal to "
            "`artifacts_count` for an ordinary run; lower when the dispatch was "
            "withheld (`publication_withheld`) or the handoff failed partway (#707). "
            "Render it beside `artifacts_count`, never instead of it — a discard is "
            "not an empty run (#853)."
        ),
    )
    publication_withheld: bool = Field(
        default=False,
        description=(
            "True when this run captured documents that were deliberately never "
            "published, because the run is FAILED. The artifacts are kept as evidence "
            "of what the source served; nothing downstream received them (#853)."
        ),
    )
    created_at: datetime
    updated_at: datetime

    model_config = ConfigDict(from_attributes=True)


class RunListItemResponse(BaseModel):
    run_id: str
    source_id: str
    source_version_id: str
    mode: RunMode
    status: RunStatus
    started_at: datetime | None
    completed_at: datetime | None
    artifacts_count: int
    captured_resources_count: int
    failure_reason: str | None
    refused: bool = Field(
        default=False,
        description=(
            "True when the ADR-0030 two-key lock blocked this dispatch (#634). "
            "Filter the collection with `?refused=true` to audit refusals."
        ),
    )
    refusal_code: RunRefusalCode | None = Field(
        default=None,
        description=(
            "Why the dispatch was refused, as a code rather than a sentence (#908). "
            "`None` for a run that was not refused, and also for refusals recorded "
            "before this field existed — an absent code means 'not classified', never "
            "'not refused'; read `refused` for that. `failure_reason` keeps the prose, "
            "which is the part naming WHICH template or policy. Same shape as the "
            "ADR-0030 enablement guard's `refusals[].code` (#854), so both refusal "
            "surfaces branch the same way."
        ),
    )
    published_artifacts_count: int = Field(
        default=0,
        description=(
            "How many of `artifacts_count` reached the broker. Lower than "
            "`artifacts_count` when the dispatch was withheld or the handoff "
            "failed partway (#853, #707)."
        ),
    )
    publication_withheld: bool = Field(
        default=False,
        description=(
            "True when a FAILED run's captured documents were deliberately not published (#853)."
        ),
    )
    created_at: datetime
    updated_at: datetime
    source_name: str
    version_label: str


class RunListResponse(BaseModel):
    data: list[RunListItemResponse]
    total: int | None = None
    limit: int | None = None
    offset: int | None = None


class RunReadinessCheck(BaseModel):
    code: str
    ok: bool
    detail: str

    model_config = ConfigDict(extra="forbid")


class RunReadinessResponse(BaseModel):
    source_id: str
    source_version_id: str
    mode: RunMode
    ready: bool
    checks: list[RunReadinessCheck]

    model_config = ConfigDict(extra="forbid")


class CapturedResourceResponse(BaseModel):
    captured_resource_id: str
    run_id: str
    source_url: str
    final_url: str
    title: str | None
    content_type: str
    http_status: int | None
    discovery_depth: int | None
    checksum: str | None
    fetched_at: datetime
    created_at: datetime
    updated_at: datetime

    model_config = ConfigDict(from_attributes=True)


class CapturedResourceListResponse(BaseModel):
    data: list[CapturedResourceResponse]
    total: int
    limit: int
    offset: int


class RawArtifactResponse(BaseModel):
    artifact_id: str
    run_id: str
    source_id: str
    source_version_id: str
    storage_path: str
    content_type: str
    artifact_metadata: dict[str, Any]
    created_at: datetime
    updated_at: datetime

    model_config = ConfigDict(from_attributes=True)


class RawArtifactListResponse(BaseModel):
    data: list[RawArtifactResponse]
    total: int
    limit: int
    offset: int


class ProviderJobResponse(BaseModel):
    provider_job_id: str
    run_id: str
    provider: str
    external_job_id: str | None
    status: ProviderJobStatus
    last_event_type: str | None
    request_payload: dict[str, Any]
    response_payload: dict[str, Any]
    created_at: datetime
    updated_at: datetime

    model_config = ConfigDict(from_attributes=True)


class ProviderJobListResponse(BaseModel):
    data: list[ProviderJobResponse]
    total: int
    limit: int
    offset: int


class WebhookAcceptedResponse(BaseModel):
    status: str


class RunPreviewSummarySample(BaseModel):
    captured_resource_id: str
    title: str | None
    final_url: str
    content_type: str
    http_status: int | None
    reason: str


class RunPreviewSummaryBreakdownEntry(BaseModel):
    content_type: str
    count: int


class RunPreviewSummaryDriftCheck(BaseModel):
    name: str
    status: str
    detail: str


class RunPreviewSummaryResponse(BaseModel):
    run_id: str
    captured_url_count: int
    artifacts_count: int
    captured_resources_count: int
    pdf_count: int
    likely_decision_page_count: int
    likely_boilerplate_page_count: int
    likely_duplicate_page_count: int
    content_type_breakdown: list[RunPreviewSummaryBreakdownEntry]
    likely_decision_pages: list[RunPreviewSummarySample]
    likely_boilerplate_pages: list[RunPreviewSummarySample]
    likely_duplicate_pages: list[RunPreviewSummarySample]
    drift_checks: list[RunPreviewSummaryDriftCheck]


class RunPipelineHealthStage(BaseModel):
    stage: str
    # Now an enum, and it can be `not_applicable`. See `PipelineStageStatus`: the
    # admin invented that value in the browser because the API reported the stages a
    # dead run never reached as `pending`. The API says it itself now.
    status: PipelineStageStatus
    detail: str
    updated_at: datetime | None


class RunDecisionNote(BaseModel):
    """One operator question, answered as a code AND as text.

    The code is what an agent branches on; the text is what a person reads. Both,
    not either: prose alone forces a consumer to pattern-match English that a later
    PR may reword, and a bare code forces every client to carry its own copy of the
    sentences — which is how the same rule ends up enforced in two places with the
    weaker one winning (AGENTS.md).
    """

    code: str
    text: str


class RunStageAction(BaseModel):
    """The next action for one stage, keyed by a code.

    `stage` and `status` travel with it so a caller never has to re-join this against
    the stage list to know what it refers to.
    """

    stage: str
    status: PipelineStageStatus
    code: str
    text: str


class RunDecisionSupport(BaseModel):
    """The four questions an operator actually asks, answered server-side (#908).

    These were computed in `platform-control/admin/src/resources/runs/
    run-decision-support.ts` — in TypeScript, in the browser — so an agent, the CLI
    and alerting could reach none of it, and anything that wanted to would have to
    re-derive the same judgements in a second implementation.

    Deliberately NOT including the admin's "health has not loaded yet" branch: that
    is a client loading state, not a judgement about a run, and the server always has
    the health it is describing.
    """

    # The one-line reading of `overall_status`. Here rather than in the client for
    # the same reason as the rest: it is a judgement about the run, and a second
    # copy of the sentences is a second place for them to diverge.
    overall_summary: RunDecisionNote
    why_it_matters: RunDecisionNote
    what_is_blocked: RunDecisionNote
    what_changed_recently: RunDecisionNote
    what_happens_if_ignored: RunDecisionNote

    # The stage lists behind `what_is_blocked`, so a caller can act on them without
    # parsing the sentence they were rendered into.
    # Required, not defaulted: an absent list and an empty list must not be the
    # same wire value here. "No stage is blocked" is an answer; "the server did not
    # say" is not, and a consumer cannot tell them apart from an omitted field.
    blocked_stages: list[str]
    never_running_stages: list[str]

    next_actions: list[RunStageAction]


class RunUnterminatedUnit(BaseModel):
    """One processing unit that started and never reached a terminal status."""

    processing_manifest_id: str
    document_id: str | None
    last_status: ProcessingStatus
    last_seen_at: datetime
    past_deadline: bool


class RunProcessingReconciliation(BaseModel):
    """Started processing units counted against finished ones, for this run (#1038).

    Required, never optional. An absent block and "nothing is stranded" must not be
    the same wire value, for exactly the reason `blocked_stages` above is required:
    a consumer cannot distinguish a server that did not say from a server that said
    zero — and reading the first as the second is how 116 documents stayed invisible
    for nine days while both their runs reported `completed`.
    """

    observed_units: int
    terminal_units: int
    #: The whole truth, with no time window applied.
    unterminated_units: int
    #: The actionable subset the reclaim sweep would terminate on its next pass.
    unterminated_units_past_deadline: int
    oldest_unterminated_at: datetime | None
    verdict: ProcessingReconciliationVerdict
    #: Bounded sample, oldest first. The counts above are computed over every unit,
    #: so truncating this list cannot change them or the verdict.
    unterminated: list[RunUnterminatedUnit]


class RunPipelineHealthResponse(BaseModel):
    run_id: str
    source_id: str
    source_version_id: str
    mode: RunMode
    run_status: RunStatus
    overall_status: str
    stages: list[RunPipelineHealthStage]
    processing_status_event_count: int
    document_lifecycle_event_count: int
    processing_reconciliation: RunProcessingReconciliation
    decision_support: RunDecisionSupport
