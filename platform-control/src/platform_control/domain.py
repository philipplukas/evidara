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
    PREVIEW = "preview"
    PRODUCTION = "production"


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
    LEGIFRANCE = "legifrance"


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


class ReviewTaskStatus(StrEnum):
    PENDING = "pending"
    COMPLETED = "completed"
    FAILED = "failed"


class CorrectionType(StrEnum):
    """Kinds of operator corrections recorded against a downstream entity.

    ``FIELD_EDIT`` rewrites one or more fields on the target entity overlay.
    ``ANNOTATION`` attaches a free-form note without mutating the entity.
    ``REJECT`` flags the entity as invalid (e.g. a hallucinated commentary
    insight). ``RESCORE_REQUEST`` asks document-intelligence to recompute
    confidence for the entity without changing user-visible content.
    """

    FIELD_EDIT = "field_edit"
    ANNOTATION = "annotation"
    REJECT = "reject"
    RESCORE_REQUEST = "rescore_request"


class CorrectionStatus(StrEnum):
    """Workflow status for a queued correction.

    ``PENDING`` is the default for newly created rows. ``APPLIED`` is set after
    the correction has been successfully written to the target entity overlay
    (or otherwise resolved, e.g. for ``ANNOTATION`` / ``REJECT``).
    ``REJECTED`` is reserved for operator review workflows that explicitly
    reject a queued correction.
    """

    PENDING = "pending"
    APPLIED = "applied"
    REJECTED = "rejected"


class CorrectionTargetEntityType(StrEnum):
    """Entity types that can carry a correction overlay.

    Sprint-1 only supports ``COMMENTARY_INSIGHT``. Adding more entity types
    is a follow-up — the column is intentionally an open string in storage so
    new values land without a migration, but the enum is the validated surface.
    """

    COMMENTARY_INSIGHT = "commentary_insight"


class CommentaryInsightReviewState(StrEnum):
    """Mirror of the contract's ``review_state`` enum.

    Kept locally on the overlay row so operator edits can transition the value
    without round-tripping the canonical document-intelligence emitter.
    """

    MACHINE_GENERATED_UNREVIEWED = "machine_generated_unreviewed"
    MACHINE_VERIFIED = "machine_verified"
    EDITOR_APPROVED = "editor_approved"
    REJECTED = "rejected"
    STALE = "stale"
