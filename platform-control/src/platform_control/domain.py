from __future__ import annotations

from collections.abc import Sequence
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


#: Statuses that END a document's processing. Nothing further is coming for a
#: document that holds one of these, whatever the outcome was.
#:
#: The complement — `ACCEPTED` and `PROCESSING` — is where #1038 lives: those two
#: mean *in flight*, and they also mean *the worker died holding this*, and until
#: something writes a terminal row nothing in the stack can tell the two apart.
#: That is #958's "absent is not broken" in the middle of the pipeline. The set is
#: named here, beside the enum, so the reconciler and the reclaimer read the same
#: definition rather than each carrying a literal list that can drift.
TERMINAL_PROCESSING_STATUSES = frozenset(
    {
        ProcessingStatus.CANONICAL_READY,
        ProcessingStatus.FAILED,
        ProcessingStatus.WITHDRAWN,
        ProcessingStatus.SKIPPED_DUPLICATE,
        ProcessingStatus.QUARANTINED,
    }
)

#: The two non-terminal statuses, derived rather than re-listed. A status added to
#: `ProcessingStatus` and to neither set would be silently treated as in-flight
#: forever; `test_every_processing_status_is_classified` fails when that happens.
NON_TERMINAL_PROCESSING_STATUSES = frozenset(ProcessingStatus) - TERMINAL_PROCESSING_STATUSES


class ProcessingReconciliationVerdict(StrEnum):
    """What a run's processing ledger says when accepted units are counted against
    terminal ones (#1038).

    There are three outcomes and deliberately no fourth. In particular there is no
    "not applicable": the acquisition reconciler (`coverage_reconciliations`)
    reported both of the runs that stranded 58 documents each as fully reconciled,
    because it reconciles what *discovery* found against what the source publishes
    and never looks at processing at all. A verdict that can decline the case it
    exists for is decoration.
    """

    #: Every processing unit this run started reached a terminal status.
    RECONCILED = "reconciled"
    #: At least one unit started and never terminated. Actionable, always.
    UNTERMINATED = "unterminated"
    #: The run has no processing rows at all. NOT the same as `RECONCILED`, and not
    #: a pass: a run that published bundle events and produced no status row is a
    #: worker that died before it said anything. Zero over zero is unknown, not
    #: clean.
    NOTHING_OBSERVED = "nothing_observed"


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

    NO_SOURCE         no source exists for this jurisdiction AND no blueprint
                      template names it, so registering one is a repo edit and a
                      deploy (#736) — not something this queue's actions can express.
    NO_SOURCE_TEMPLATE_AVAILABLE
                      no source exists, but a template DOES name this jurisdiction, so
                      registering one is an API call against a blueprint an author
                      already wrote. The distinction is the whole of the difference
                      between work an agent may do and work that needs a person: the
                      judgement — which portal, which provider, which trust tier — was
                      made when the template was authored, not now.
    NO_DENOMINATOR    a source exists but nothing has told us how much this
                      jurisdiction publishes, so no claim about coverage is possible.
                      It blocks every other answer *about that jurisdiction*, which is
                      why it sorts ahead of the gaps.
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

    NO_SOURCE = "no_source"
    NO_SOURCE_TEMPLATE_AVAILABLE = "no_source_template_available"
    NO_DENOMINATOR = "no_denominator"
    NEVER_ACQUIRED = "never_acquired"
    ACQUISITION_GAP = "acquisition_gap"
    PROCESSING_GAP = "processing_gap"
    HOLDINGS_EXCEED_DENOMINATOR = "holdings_exceed_denominator"
    REFUSALS_OUTSTANDING = "refusals_outstanding"


class CoverageWorkAction(StrEnum):
    """What a coverage-queue item implies should happen next.

    This vocabulary already existed — in `tools/evidara-cli`'s `agent_loop.py`, in
    Python, reachable only by that one client. #964: a second client had to either
    re-derive it or copy it, and the copy is where the two disagreed.

    It lives here now so there is one definition and both the CLI and the operator
    panel read it (ADR-0056 constraint 1). The values are unchanged from the CLI's,
    so nothing consuming them has to relearn a vocabulary.

    REGISTER_SOURCE       no source exists and no template names this jurisdiction.
                          Registering one is a repo edit and a deploy (#736).
    REGISTER_SOURCE_FROM_TEMPLATE
                          no source exists, but a template does. Creating one is an
                          API call that produces a DRAFT source version — which a
                          person still approves before any production run, so the
                          agent's reach ends well short of acquiring anything.
    ENUMERATE_DENOMINATOR nothing has told us how much this jurisdiction publishes.
                          Every other answer about it is unstatable until this exists.
    RUN_ACCEPTANCE        a denominator exists and we hold less than it. An acceptance
                          run is the evidence primitive (ADR-0030).
    AWAIT_PIPELINE        captured, not yet processed. Wait and re-check — running
                          acquisition again adds to a backlog rather than clearing it.
    INVESTIGATE_HOLDINGS  we hold more than the source claims to publish. A dedup
                          failure or a denominator counting something else. No run
                          fixes it.
    RESOLVE_REFUSAL       a run here was refused. The refusal is the answer, and a
                          person decides what happens next.
    """

    REGISTER_SOURCE = "register_source"
    REGISTER_SOURCE_FROM_TEMPLATE = "register_source_from_template"
    ENUMERATE_DENOMINATOR = "enumerate_denominator"
    RUN_ACCEPTANCE = "run_acceptance"
    AWAIT_PIPELINE = "await_pipeline"
    INVESTIGATE_HOLDINGS = "investigate_holdings"
    RESOLVE_REFUSAL = "resolve_refusal"


class CoverageWorkActor(StrEnum):
    """Who may carry out a queue item's action.

    Not a UI convention — the autonomy boundary, stated where every client reads the
    same answer. #854 already moved the ADR-0030 two-key guard server-side; this is
    the same idea one step earlier, for work that has not reached the key yet.

    AGENT  the agent may carry this out on its own.
    HUMAN  doing something is the wrong response, and a person decides.
    """

    AGENT = "agent"
    HUMAN = "human"


#: Actions that belong to a person, never to the agent.
#:
#: Both refusal and holdings-exceeding-denominator are cases where *acting* is the
#: wrong move: a refusal is a decision to respect — a closed config key is how an
#: operator stops traffic at a portal when an authority complains about load — and
#: holdings above a denominator is a measurement problem no run resolves.
#: `register_source` needs a deploy, which no queue action can express.
#:
#: `register_source_from_template` is deliberately NOT here. It was the same action
#: until templates declared a jurisdiction, and the sentence above is exactly why the
#: two had to split: "needs a deploy" is true with no template and false with one.
#: What the agent may then do is bounded three ways that do not depend on this set —
#: it creates a DRAFT source version, a person approves the version before any
#: production run (ADR-0030), and the two-key lock still refuses a run whose provider
#: or config key is not ready.
HUMAN_ONLY_ACTIONS: frozenset[CoverageWorkAction] = frozenset(
    {
        CoverageWorkAction.RESOLVE_REFUSAL,
        CoverageWorkAction.INVESTIGATE_HOLDINGS,
        CoverageWorkAction.REGISTER_SOURCE,
    }
)


#: Reason -> action. Ordered by what most constrains the response, which is NOT the
#: same as `_WORK_REASON_ORDER` in `coverage_service`, and #964 is what happens when
#: the two are assumed to be one thing.
#:
#: They answer different questions and both are correct:
#:   * `_WORK_REASON_ORDER` decides how the queue is SORTED — most blocking first,
#:     so an operator reads the worst thing at the top.
#:   * this order decides what may be DONE, so a refusal outranks a gap. Under the
#:     sort order, a jurisdiction whose every run was refused (`refusals_outstanding`
#:     + `never_acquired`, the normal shape of a refusal) resolved to `run_acceptance`
#:     — an agent retrying work a person had refused.
#:
#: The safety answer does not actually depend on this order any more; see
#: `resolve_work_actor`, which folds over every reason rather than the first. The
#: order decides only which action is NAMED.
REASON_ACTION_PRIORITY: tuple[tuple[CoverageWorkReason, CoverageWorkAction], ...] = (
    (CoverageWorkReason.NO_SOURCE, CoverageWorkAction.REGISTER_SOURCE),
    (
        CoverageWorkReason.NO_SOURCE_TEMPLATE_AVAILABLE,
        CoverageWorkAction.REGISTER_SOURCE_FROM_TEMPLATE,
    ),
    (CoverageWorkReason.NO_DENOMINATOR, CoverageWorkAction.ENUMERATE_DENOMINATOR),
    (CoverageWorkReason.REFUSALS_OUTSTANDING, CoverageWorkAction.RESOLVE_REFUSAL),
    (
        CoverageWorkReason.HOLDINGS_EXCEED_DENOMINATOR,
        CoverageWorkAction.INVESTIGATE_HOLDINGS,
    ),
    (CoverageWorkReason.NEVER_ACQUIRED, CoverageWorkAction.RUN_ACCEPTANCE),
    (CoverageWorkReason.ACQUISITION_GAP, CoverageWorkAction.RUN_ACCEPTANCE),
    (CoverageWorkReason.PROCESSING_GAP, CoverageWorkAction.AWAIT_PIPELINE),
)


def resolve_work_action(reasons: Sequence[CoverageWorkReason]) -> CoverageWorkAction:
    """The action to NAME for a set of reasons: the most constraining one present."""
    present = set(reasons)
    for reason, action in REASON_ACTION_PRIORITY:
        if reason in present:
            return action
    # Unreachable while every enum member is mapped, which
    # `test_every_reason_maps_to_an_action` enforces. Refusing beats guessing.
    raise ValueError(f"no action mapped for reasons: {sorted(r.value for r in reasons)}")


def resolve_work_actor(reasons: Sequence[CoverageWorkReason]) -> CoverageWorkActor:
    """Who may act, folded over EVERY reason rather than the first one that matches.

    This is deliberately not `resolve_work_action(...) in HUMAN_ONLY_ACTIONS`. A
    first-match rule makes the autonomy boundary depend on an ordering, and #964 is
    that dependency going wrong in a real client. Folding means a human-only reason
    anywhere in the set makes the item human-only, whatever it is named — so
    reordering `REASON_ACTION_PRIORITY` can change a label but can never hand the
    agent work a person owns.

    It also stays true to `CoverageWorkReason`'s own rule that the queue ships no
    ranking: every reason is consulted, none outranks the others for this answer.
    """
    for reason in reasons:
        for mapped_reason, action in REASON_ACTION_PRIORITY:
            if mapped_reason is reason and action in HUMAN_ONLY_ACTIONS:
                return CoverageWorkActor.HUMAN
    return CoverageWorkActor.AGENT


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
