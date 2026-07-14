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
    CANTON_HTTP = "canton_http"
    LEGIFRANCE = "legifrance"
    CH_COURT_DECISIONS = "ch_court_decisions"


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


class ReviewTaskStatus(StrEnum):
    PENDING = "pending"
    COMPLETED = "completed"
    FAILED = "failed"
