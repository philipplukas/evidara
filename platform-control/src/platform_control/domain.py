from __future__ import annotations

from enum import StrEnum


class SourceStatus(StrEnum):
    ACTIVE = "active"
    INACTIVE = "inactive"
    ARCHIVED = "archived"


class SourceVersionStatus(StrEnum):
    DRAFT = "draft"
    PENDING_APPROVAL = "pending_approval"
    APPROVED = "approved"
    REJECTED = "rejected"
    SUPERSEDED = "superseded"


class RunStatus(StrEnum):
    PENDING = "pending"
    RUNNING = "running"
    COMPLETED = "completed"
    FAILED = "failed"
    CANCELLED = "cancelled"


class RunMode(StrEnum):
    """What a run is *for*, which decides which ADR-0030 keys it needs.

    ``ACCEPTANCE`` is the operator's rehearsal against the live portal — the run
    that produces the evidence for turning the keys, so it cannot require them to
    be turned already. It admits a provider in ``AWAITING_EVIDENCE`` (never a
    scaffold) and does not require the config key, because flipping that key is
    the *outcome* of the acceptance, not its precondition. It is recorded on the
    run so evidence is self-labelling and can never be mistaken for production
    ingest afterwards.
    """

    PREVIEW = "preview"
    PRODUCTION = "production"
    ACCEPTANCE = "acceptance"


class RunScopeKind(StrEnum):
    FULL_SOURCE = "full_source"
    DISCOVERED_SUBSET = "discovered_subset"
    SOURCE_SNAPSHOT = "source_snapshot"
    TIME_WINDOW = "time_window"


class RunReplayMode(StrEnum):
    PARTIAL_RERUN = "partial_rerun"
    BACKFILL = "backfill"
    FULL_REFRESH = "full_refresh"


class ProviderJobStatus(StrEnum):
    ACCEPTED = "accepted"
    RUNNING = "running"
    COMPLETED = "completed"
    FAILED = "failed"


class FirecrawlMode(StrEnum):
    CRAWL = "crawl"
    BATCH_SCRAPE = "batch_scrape"


class AcquisitionProvider(StrEnum):
    FIRECRAWL = "firecrawl"
    DETERMINISTIC_HTTP = "deterministic_http"
    FEDLEX_SPARQL = "fedlex_sparql"
    RIS_OGD = "ris_ogd"
    EUR_LEX_SPARQL = "eur_lex_sparql"
    BUNDESLAND_HTTP = "bundesland_http"
    REGIONE_HTTP = "regione_http"
    CANTON_HTTP = "canton_http"
    LEXFIND_API = "lexfind_api"
    GEMEINDE_HTTP = "gemeinde_http"
    LEGIFRANCE = "legifrance"
    CH_COURT_DECISIONS = "ch_court_decisions"


# NOTE: this docstring is a GENERATED contract surface — it is copied verbatim
# into `contracts/api/platform-control.openapi.yaml`, so editing it forces a
# manifest version bump (ADR-0034). It is therefore deliberately left as-is while
# three open PRs (#844, #851, #864) already claim that bump. What `STRICT`
# enforces in full — `Disallow`/`Allow` AND the site's `Crawl-delay` /
# `Request-rate` — is documented at the top of
# `platform_control.services.robots`, which is the module that enforces it. The
# text below under-claims rather than over-claims, which is the safe direction.
class RobotsMode(StrEnum):
    """How aggressively a jurisdiction's scrapers honour robots.txt.

    ``STRICT`` (default) means the crawler must refuse any URL robots.txt
    disallows. ``IGNORE`` is reserved for sources where we have an explicit
    open-data licence that supersedes robots (e.g. Fedlex, RIS OGD).
    """

    STRICT = "strict"
    IGNORE = "ignore"


class ExecutionMode(StrEnum):
    """Run-time execution posture for a source version.

    ``LIVE`` dispatches to the configured provider normally. ``SHADOW`` wires the
    full scheduler + workflow + webhook path but substitutes a fixture-backed
    provider so a new jurisdiction can be exercised end-to-end without touching
    the upstream server. ``OFF`` disables scheduled runs entirely.
    """

    OFF = "off"
    SHADOW = "shadow"
    LIVE = "live"


class ProcessingStatus(StrEnum):
    ACCEPTED = "accepted"
    PROCESSING = "processing"
    CANONICAL_READY = "canonical_ready"
    FAILED = "failed"
    WITHDRAWN = "withdrawn"
    SKIPPED_DUPLICATE = "skipped_duplicate"
    #: Terminal refusal (ADR-0047, #731). The bundle was structurally valid and
    #: processing did not fail — document-intelligence looked at the extracted
    #: text and could not support the claim that it is law: a scan with no text
    #: layer, a cover sheet, an empty text layer.
    #:
    #: Distinct from FAILED on purpose. A failure's remedy is replay; a
    #: quarantine's is implementing the missing document class, and replaying it
    #: changes nothing. Distinct from SKIPPED_DUPLICATE because nothing was
    #: published and there is no prior document to point at.
    QUARANTINED = "quarantined"


#: Statuses that must carry `error_code` and `error_summary`, and that no other
#: status may carry. Both are refusals the operator has to be able to act on, and
#: a refusal without a stated reason is the silence ADR-0047 exists to end.
STATUSES_REQUIRING_A_REASON = frozenset({ProcessingStatus.FAILED, ProcessingStatus.QUARANTINED})


class NormLevel(StrEnum):
    """Rank of a norm in the hierarchy of norms (ADR-0033).

    A *jurisdiction* carries the level its own legislation sits at; a
    *document* inherits that level unless the canonical metadata declares a
    higher rank (only ``CONSTITUTIONAL`` can be declared this way — a
    constitution is enacted by a federal jurisdiction but outranks its
    ordinary statutes, so it cannot be derived from the jurisdiction alone).

    Ordering is authoritative and lives in
    ``contracts/vocabularies/norm-level.json``; ``NORM_LEVEL_RANK`` below is
    the Python mirror. Lower rank = higher authority.
    """

    CONSTITUTIONAL = "constitutional"
    INTERNATIONAL = "international"
    FEDERAL = "federal"
    CANTONAL = "cantonal"
    MUNICIPAL = "municipal"


#: Lower rank = higher authority. Mirrors `contracts/vocabularies/norm-level.json`.
#: `international` is placed above ordinary federal statutes per the monist
#: reading of BV Art. 5(4); see the vocabulary file for the caveat.
NORM_LEVEL_RANK: dict[NormLevel, int] = {
    NormLevel.CONSTITUTIONAL: 10,
    NormLevel.INTERNATIONAL: 20,
    NormLevel.FEDERAL: 30,
    NormLevel.CANTONAL: 40,
    NormLevel.MUNICIPAL: 50,
}


class DocumentLifecycleStatus(StrEnum):
    ACTIVE = "active"
    SUPERSEDED = "superseded"
    REPEALED = "repealed"
    WITHDRAWN = "withdrawn"


class DocumentWithdrawalReason(StrEnum):
    DUPLICATE = "duplicate"
    INVALID_SOURCE = "invalid_source"
    RIGHTS_RESTRICTED = "rights_restricted"
    OPERATOR_WITHDRAWN = "operator_withdrawn"


class SearchDisposition(StrEnum):
    REMOVE = "remove"
    HIDE = "hide"


class WizardProjectStatus(StrEnum):
    DRAFT = "draft"
    ACTIVE = "active"
    ARCHIVED = "archived"


class WizardRunState(StrEnum):
    DRAFT_SCOPE = "DraftScope"
    DISCOVERY_PLAN = "DiscoveryPlan"
    PILOT_RUN = "PilotRun"
    HUMAN_GATE_APPROVAL = "HumanGateApproval"
    SCALED_RUN = "ScaledRun"
    REVIEW_ROUTING = "ReviewRouting"
    FINALIZE_PUBLISH = "FinalizePublish"
    MONITOR_AND_DRIFT = "MonitorAndDrift"
    #: Terminal. Nobody approved or rejected the human gate before it expired (#560).
    #:
    #: The gate used to be an unbounded `wait_condition`, so an un-actioned run sat
    #: at `HumanGateApproval` forever — the workflow open, the DB frozen, and no
    #: way to tell "waiting on an operator" from "abandoned in March". This is the
    #: state that distinguishes them, and it is the *only* thing an expired gate
    #: may become: the fallback is always to refuse to scale, never to auto-approve
    #: a fan-out of crawls against live government portals.
    #:
    #: Terminal on purpose. Resuming means a new pilot, which is a new operator
    #: decision, not a continuation of one nobody made.
    GATE_EXPIRED = "GateExpired"


class ReviewTaskStatus(StrEnum):
    PENDING = "pending"
    COMPLETED = "completed"
    FAILED = "failed"


class RunRefusalCode(StrEnum):
    """Why a run dispatch was refused, as a code rather than a sentence.

    `_record_refused_run` has always written the reason as `str(exc)` — English
    prose, in `failure_reason`. A human reads that fine; an agent has to pattern-match
    it, and a message reworded in a later PR silently breaks every matcher. The
    ADR-0030 enablement guard already returns machine-readable `refusals[].code`
    (#854); run refusals now match it, so both refusal surfaces can be branched on
    the same way (#908).

    The prose is kept, not replaced: `failure_reason` still carries the exception's
    own message, which is the part that says *which* template or policy.
    """

    BLUEPRINT_TEMPLATE_NOT_ENABLED = "blueprint_template_not_enabled"
    COMPLIANCE_POLICY_MISSING = "compliance_policy_missing"
    PROVIDER_NOT_LIVE_READY = "provider_not_live_ready"


class PipelineStageStatus(StrEnum):
    """The status of one pipeline stage, including the one the API used to omit.

    `NOT_APPLICABLE` is the value this enum exists for. A run that ended `failed` or
    `cancelled` will never advance, but `get_pipeline_health` reported the stages it
    never reached as `pending` — with copy like "Awaiting DI processing signal before
    projection stage starts", which reads as *work is still coming* over a run that is
    dead. The admin had been re-labelling those in the browser since #649. That is a
    correctness fix applied in one client, so every other consumer — the CLI, an
    agent, alerting — still saw the misleading answer (#908).
    """

    OK = "ok"
    PENDING = "pending"
    # `in_progress`, not `running`: this is the value the stage resolvers have always
    # emitted, and `test_run_pipeline_health_endpoint_returns_stage_summary` caught the
    # guess. Enumerating the set is how a wrong assumption becomes a failing test
    # instead of a field consumers quietly mis-handle.
    IN_PROGRESS = "in_progress"
    BLOCKED = "blocked"
    FAILED = "failed"
    NOT_APPLICABLE = "not_applicable"


class CoverageWorkReason(StrEnum):
    """Why a jurisdiction appears in the coverage work queue.

    The queue exists because population at scale is a loop over *"what should we hold
    that we don't"* — and without a stated reason a queue is just a list, which an
    operator or an agent has to re-derive the meaning of every time.

    Deliberately NOT a priority score. ADR-0042 rejected a completeness percentage
    because "every such number needs a denominator", and a priority number has exactly
    the same defect: it reads as measured and is invented. A jurisdiction carries the
    reasons that are true of it, the counts behind them travel alongside, and the caller
    decides what matters.

    NO_DENOMINATOR    nothing has told us how much this jurisdiction publishes, so no
                      claim about coverage is possible at all. This is the one reason
                      that blocks every other answer, which is why it sorts first.
    NEVER_ACQUIRED    a denominator may or may not exist; nothing has been captured.
    ACQUISITION_GAP   the source says there is more than we have captured.
    PROCESSING_GAP    we captured it and the pipeline has not turned it into documents.
    HOLDINGS_EXCEED_DENOMINATOR
                      we hold MORE than the source claims to publish. Not "done" — a
                      finding: a dedup failure, or a denominator counting something
                      else. The schema already refuses to clamp a negative gap for the
                      same reason.
    REFUSALS_OUTSTANDING
                      runs were refused here and nobody has resolved them. A refusal is
                      a decision waiting for an operator, not a failure to retry.
    """

    NO_DENOMINATOR = "no_denominator"
    NEVER_ACQUIRED = "never_acquired"
    ACQUISITION_GAP = "acquisition_gap"
    PROCESSING_GAP = "processing_gap"
    HOLDINGS_EXCEED_DENOMINATOR = "holdings_exceed_denominator"
    REFUSALS_OUTSTANDING = "refusals_outstanding"


class DenominatorTier(StrEnum):
    """How trustworthy a coverage denominator is — and therefore what may be claimed.

    A ledger that reports "100%" against an unknown denominator is worse than no ledger:
    it manufactures the false green this repo keeps getting caught by. So the tier travels
    with every expected count, and it decides what the number is allowed to support.

    PUBLISHED  the source states its own count (LexFind `entities/extended`).
               Completeness is claimable, with a gap.
    REGISTRY   we know the UNITS but not their contents — 2110 seeded communes, whose
               individual law counts nobody publishes. Breadth only. A gap here would
               subtract documents from units and yield a number in no unit at all.
    NONE       no denominator exists. Completeness is unstatable; the held count is the
               only honest output.
    """

    PUBLISHED = "published"
    REGISTRY = "registry"
    NONE = "none"


class CoverageAttributionStatus(StrEnum):
    """Whether a reconciliation could be tied to a jurisdiction.

    Providers speak their own entity ids (LexFind `26`), never `jur_ch_zh`; the mapping
    exists only through `Source.jurisdiction_id`, which holds one jurisdiction. A run
    covering several entities therefore cannot be attributed without inventing the split.

    Following the `Run.refused` precedent, the unattributable case is still WRITTEN —
    the attempt leaves evidence rather than silence, so it can be counted and explained
    rather than looking like a run that never measured anything.
    """

    ATTRIBUTED = "attributed"
    AMBIGUOUS_MULTI_ENTITY = "ambiguous_multi_entity"
