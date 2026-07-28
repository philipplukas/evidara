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
