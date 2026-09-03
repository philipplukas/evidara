"""Pure logic for the coverage loop (ADR-0030, ADR-0033).

The coverage loop is the operator path that brings a new corpus online:

    blueprint template -> source + version -> readiness -> approve version ->
    acceptance run -> DI processing -> searchable -> evidence -> `enabled: true`

Everything in this module is a pure function over JSON already returned by
platform-control. No HTTP, no side effects, so the branching an agent depends on is
unit-testable without a stack.

**This is not ADR-0033 step 6.** ADR-0033 §4 forbids building the MCP server before the
platform underneath it exists. Nothing here is a protocol server or a legal-reasoning
tool; it reads operator read models platform-control already publishes and names, in
machine-readable form, *why* a template is inert and *who* can unblock it.

## Why the classification lives here at all

`GET /v1/runs/readiness` is authoritative for a source version that already exists, but
every failing two-key-lock outcome shares one code, `acquisition_lock_open`, and the
discriminating information is English prose in `detail`
(`platform-control/src/platform_control/services/run_service.py:456-591`). Branching on
that prose is exactly what issue #745 point 3 warns against.

The blueprint-template read model, however, *is* discriminated: `acquisition_readiness`
is the three-state code key and `enabled` + `source` carry the config key and its
provenance (`platform-control/src/platform_control/schemas/source.py:503-556`). So the
blocker kind is derivable without string-matching English, and that derivation is what
lives here.

The cost is a third copy of the lock rule — platform-control already warns that its own
two copies must be edited together (`run_service.py:443-450`). This copy therefore
**never asserts on its own**: `classify_template` cross-checks its derivation against the
server's `launchable` field and sets `agrees_with_server: false` when they diverge, and
the commands surface that as a failure rather than trusting the client. Where a source
version exists, prefer `/v1/runs/readiness`.
"""

from __future__ import annotations

from typing import Any

from evidara_cli.gate_coverage import gate_coverage_verdict

# --- ADR-0030 code key (provider readiness) --------------------------------------
READINESS_SCAFFOLD = "scaffold"
READINESS_AWAITING_EVIDENCE = "awaiting_evidence"
READINESS_LIVE = "live"
KNOWN_READINESS = (READINESS_SCAFFOLD, READINESS_AWAITING_EVIDENCE, READINESS_LIVE)

# --- ADR-0030 config key (template enablement) -----------------------------------
CONFIG_KEY_OPEN = "open"
CONFIG_KEY_CLOSED_BY_OPERATOR = "closed_by_operator"
CONFIG_KEY_NEVER_TURNED = "never_turned"

# --- Derived lock state ----------------------------------------------------------
LOCK_OPEN = "open"
LOCK_ACCEPTANCE_ONLY = "acceptance_only"
LOCK_CLOSED = "closed"

# --- Blocker kinds (the thing an agent should branch on) -------------------------
BLOCKER_PROVIDER_SCAFFOLD = "provider_scaffold"
BLOCKER_PROVIDER_AWAITING_EVIDENCE = "provider_awaiting_evidence"
BLOCKER_TEMPLATE_DISABLED_BY_OPERATOR = "template_disabled_by_operator"
BLOCKER_TEMPLATE_NEVER_ENABLED = "template_never_enabled"

# --- Remedies (who unblocks it) ---------------------------------------------------
REMEDY_NONE = "none"
REMEDY_ENGINEERING = "engineering"
REMEDY_RUN_ACCEPTANCE_LOOP = "run_acceptance_loop"
REMEDY_REOPEN_CONFIG_KEY = "reopen_config_key"

# --- Run modes -------------------------------------------------------------------
MODE_PREVIEW = "preview"
MODE_PRODUCTION = "production"
MODE_ACCEPTANCE = "acceptance"

TERMINAL_RUN_STATUSES = frozenset({"completed", "failed", "cancelled"})

_REMEDY_TEXT = {
    BLOCKER_PROVIDER_SCAFFOLD: (
        "The provider cannot acquire its targets yet. This needs engineering; no run "
        "mode will dispatch (ADR-0030 §1)."
    ),
    BLOCKER_PROVIDER_AWAITING_EVIDENCE: (
        "The provider is implemented but no acceptance run has been captured. Dispatch a "
        "run with mode=acceptance to capture it — this does not need an engineer "
        "(ADR-0030 §6)."
    ),
    BLOCKER_TEMPLATE_DISABLED_BY_OPERATOR: (
        "An operator explicitly turned the config key off. Acceptance mode does NOT waive "
        "an operator's kill switch. Ask them first; reopening it is `evidara workflow "
        "coverage enable --reopen-operator-kill-switch` (or the admin panel's Blueprints "
        "inventory) (ADR-0030 §2)."
    ),
    BLOCKER_TEMPLATE_NEVER_ENABLED: (
        "The config key has never been turned. Acceptance mode waives it, so capture "
        "acceptance-run evidence with mode=acceptance, then flip `enabled: true` "
        "(ADR-0030 §5)."
    ),
}


def normalise_readiness(value: Any) -> str:
    """Coerce an ``acquisition_readiness`` value, failing closed on anything unknown.

    Mirrors ``provider_readiness()``: an unrecognised or absent state is treated as
    ``scaffold``, never as something that may dispatch.
    """
    text = str(value or "").strip().lower()
    return text if text in KNOWN_READINESS else READINESS_SCAFFOLD


def config_key_state(*, enabled: Any, provenance: Any) -> str:
    """Classify the ADR-0030 config key.

    ``provenance`` is the template's ``source`` field: ``override`` means an operator
    wrote the value, ``default`` means it is the shipped ``source_blueprints.yaml``
    value nobody has touched. The distinction is load-bearing — acceptance mode waives
    a key that was never turned but never one an operator explicitly closed (#768).
    """
    if bool(enabled):
        return CONFIG_KEY_OPEN
    if str(provenance or "default").strip().lower() == "override":
        return CONFIG_KEY_CLOSED_BY_OPERATOR
    return CONFIG_KEY_NEVER_TURNED


def dispatchable_modes(*, readiness: str, config_key: str) -> list[str]:
    """Run modes the two-key lock would admit for this template.

    Mirrors ``RunService._require_launchable``. Ordered least- to most-privileged so
    ``[0]`` is always the safest mode that works.
    """
    if readiness == READINESS_SCAFFOLD:
        return []
    if config_key == CONFIG_KEY_CLOSED_BY_OPERATOR:
        return []
    if readiness == READINESS_AWAITING_EVIDENCE:
        return [MODE_ACCEPTANCE]
    if config_key == CONFIG_KEY_NEVER_TURNED:
        return [MODE_ACCEPTANCE]
    return [MODE_ACCEPTANCE, MODE_PREVIEW, MODE_PRODUCTION]


def classify_template(template: dict[str, Any]) -> dict[str, Any]:
    """Turn one blueprint-template read model into a machine-readable lock verdict.

    Returns a dict carrying the identity fields, both key states, the derived blocker
    and remedy, the modes that would dispatch, and ``agrees_with_server`` — see the
    module docstring for why that last field exists.
    """
    readiness = normalise_readiness(template.get("acquisition_readiness"))
    config_key = config_key_state(
        enabled=template.get("enabled"),
        provenance=template.get("source"),
    )
    modes = dispatchable_modes(readiness=readiness, config_key=config_key)

    blocker: str | None
    remedy: str
    if readiness == READINESS_SCAFFOLD:
        blocker, remedy = BLOCKER_PROVIDER_SCAFFOLD, REMEDY_ENGINEERING
    elif config_key == CONFIG_KEY_CLOSED_BY_OPERATOR:
        blocker, remedy = BLOCKER_TEMPLATE_DISABLED_BY_OPERATOR, REMEDY_REOPEN_CONFIG_KEY
    elif readiness == READINESS_AWAITING_EVIDENCE:
        blocker, remedy = BLOCKER_PROVIDER_AWAITING_EVIDENCE, REMEDY_RUN_ACCEPTANCE_LOOP
    elif config_key == CONFIG_KEY_NEVER_TURNED:
        blocker, remedy = BLOCKER_TEMPLATE_NEVER_ENABLED, REMEDY_RUN_ACCEPTANCE_LOOP
    else:
        blocker, remedy = None, REMEDY_NONE

    if not modes:
        lock_state = LOCK_CLOSED
    elif blocker is None:
        lock_state = LOCK_OPEN
    else:
        lock_state = LOCK_ACCEPTANCE_ONLY

    derived_launchable = blocker is None
    server_launchable = template.get("launchable")
    agrees = server_launchable is None or bool(server_launchable) is derived_launchable

    return {
        "overlay_id": template.get("overlay_id"),
        "provider_template_id": template.get("provider_template_id"),
        "provider": template.get("provider"),
        "code_key": readiness,
        "config_key": config_key,
        "lock_state": lock_state,
        "blocker": blocker,
        "remedy": remedy,
        "remedy_detail": _REMEDY_TEXT.get(blocker) if blocker else None,
        "dispatchable_modes": modes,
        "recommended_mode": modes[0] if modes else None,
        "launchable": derived_launchable,
        "server_launchable": server_launchable,
        "agrees_with_server": agrees,
        # Prose from platform-control, kept verbatim for humans. Never branch on it.
        "notes": list(template.get("notes") or []),
    }


def summarise_templates(classified: list[dict[str, Any]]) -> dict[str, Any]:
    """Aggregate counts an operator uses to pick the next thing to work on."""
    by_blocker: dict[str, int] = {}
    by_readiness: dict[str, int] = {}
    for item in classified:
        key = item["blocker"] or "none"
        by_blocker[key] = by_blocker.get(key, 0) + 1
        by_readiness[item["code_key"]] = by_readiness.get(item["code_key"], 0) + 1
    return {
        "total": len(classified),
        "launchable": sum(1 for i in classified if i["launchable"]),
        "acceptance_ready": sum(
            1 for i in classified if MODE_ACCEPTANCE in i["dispatchable_modes"]
        ),
        "needs_engineering": by_blocker.get(BLOCKER_PROVIDER_SCAFFOLD, 0),
        "by_blocker": by_blocker,
        "by_readiness": by_readiness,
        "disagreements_with_server": sum(1 for i in classified if not i["agrees_with_server"]),
    }


# ---------------------------------------------------------------------------------
# Stall diagnosis
# ---------------------------------------------------------------------------------

STALL_RUN_REFUSED = "run_refused_by_lock"
STALL_NO_DISPATCH_WORKER = "no_dispatch_worker"
STALL_PUBLISH_PATH_DISABLED = "publish_path_disabled"
STALL_DI_CONSUMER_SILENT = "di_consumer_silent"
STALL_PROJECTION_STALLED = "projection_stalled"
STALL_SEARCH_PENDING = "search_projection_pending"
STALL_UNKNOWN = "unknown"

_STALL_DETAIL = {
    STALL_RUN_REFUSED: (
        "The run was refused by the ADR-0030 two-key lock and persisted as FAILED with "
        "`refused: true`. This is not a stall — read `failure_reason` and fix the key it "
        "names. `evidara workflow coverage templates` reports which key and whose remedy."
    ),
    STALL_NO_DISPATCH_WORKER: (
        "The run was accepted but never left PENDING, so nothing dispatched it. "
        "platform-control persists the run before dispatch, so a PENDING run with no "
        "acquisition progress means no worker picked it up: check that the dispatcher for "
        "the configured `run_dispatch_backend` is actually running. A local compose stack "
        "does not start a worker for every provider."
    ),
    STALL_PUBLISH_PATH_DISABLED: (
        "Acquisition finished and captured resources, but document-intelligence received "
        "zero processing-status events. The publish path is the usual cause: "
        "PLATFORM_CONTROL_EVENT_PUBLISHER_BACKEND defaults to `noop`, so platform-control "
        "captures the documents, reports the run `completed`, and publishes nothing. Set "
        "it to `nats` (with PLATFORM_CONTROL_ARTIFACT_STORE_BACKEND=s3) and re-run."
    ),
    STALL_DI_CONSUMER_SILENT: (
        "document-intelligence acknowledged the run but has not progressed. Check the DI "
        "consumer container is up and reading the stream."
    ),
    STALL_PROJECTION_STALLED: (
        "DI reported processing but no document-lifecycle events were projected. Check "
        "the projection bridge between DI and legal-search."
    ),
    STALL_SEARCH_PENDING: (
        "Projection has run but the search stage has not reported. Give the index a moment, "
        "then assert searchability directly with `evidara legal-search search`."
    ),
    STALL_UNKNOWN: (
        "No known stall signature matched. Inspect the pipeline-health stages directly."
    ),
}


def _stage(health: dict[str, Any], name: str) -> dict[str, Any]:
    for stage in health.get("stages") or []:
        if isinstance(stage, dict) and stage.get("stage") == name:
            return stage
    return {}


def diagnose_stall(run: dict[str, Any], health: dict[str, Any]) -> dict[str, Any]:
    """Name the likely cause of a run that has not reached the requested state.

    Returns a ``cause`` code an agent can branch on plus operator-facing detail. The
    causes are the failure modes actually hit driving the loop end to end, not a
    theoretical list.
    """
    if bool(run.get("refused")):
        cause = STALL_RUN_REFUSED
    else:
        run_status = str(run.get("status") or "").lower()
        di = _stage(health, "document_intelligence")
        projection = _stage(health, "projection")
        search = _stage(health, "search")
        processing_events = int(health.get("processing_status_event_count") or 0)
        lifecycle_events = int(health.get("document_lifecycle_event_count") or 0)

        if run_status == "pending":
            cause = STALL_NO_DISPATCH_WORKER
        elif run_status == "completed" and processing_events == 0:
            cause = STALL_PUBLISH_PATH_DISABLED
        elif di.get("status") in {"pending", "in_progress"} and processing_events > 0:
            cause = STALL_DI_CONSUMER_SILENT
        elif lifecycle_events == 0 and projection.get("status") in {"pending", "in_progress"}:
            cause = STALL_PROJECTION_STALLED
        elif search.get("status") == "pending":
            cause = STALL_SEARCH_PENDING
        else:
            cause = STALL_UNKNOWN

    return {
        "cause": cause,
        "detail": _STALL_DETAIL[cause],
        "run_status": run.get("status"),
        "refused": bool(run.get("refused")),
        "failure_reason": run.get("failure_reason"),
        "overall_status": health.get("overall_status"),
        "stages": health.get("stages") or [],
    }


# ---------------------------------------------------------------------------------
# ADR-0030 acceptance-evidence verdict
# ---------------------------------------------------------------------------------

EVIDENCE_RUN_REFUSED = "run_refused_by_lock"
EVIDENCE_RUN_NOT_COMPLETED = "run_not_completed"
EVIDENCE_MODE_NOT_ACCEPTANCE = "mode_not_acceptance"
EVIDENCE_EXECUTION_MODE_SHADOW = "execution_mode_shadow"
EVIDENCE_NO_CAPTURED_RESOURCES = "no_captured_resources"

_EVIDENCE_DETAIL = {
    EVIDENCE_RUN_REFUSED: (
        "The run was refused by the two-key lock; it never reached the portal, so it "
        "evidences nothing."
    ),
    EVIDENCE_RUN_NOT_COMPLETED: ("Only a completed run can serve as acceptance evidence."),
    EVIDENCE_MODE_NOT_ACCEPTANCE: (
        "ADR-0030 §6: acceptance evidence comes from a run recorded with `mode=acceptance`, "
        "so evidence is self-labelling and cannot be mistaken for production ingest."
    ),
    EVIDENCE_EXECUTION_MODE_SHADOW: (
        "ADR-0030 §2: a SHADOW version is routed to the cassette provider and replays "
        "fixtures. It never touches the live portal, so it proves nothing about it and "
        "CANNOT serve as acceptance evidence — no matter how green it looks."
    ),
    EVIDENCE_NO_CAPTURED_RESOURCES: (
        "The run captured zero resources, so there is nothing for the gates to have asserted over."
    ),
}


def acceptance_evidence_verdict(
    *,
    run: dict[str, Any],
    execution_mode: str | None = None,
    captured_resources_count: int | None = None,
    evidence_bundle: dict[str, Any] | None = None,
) -> dict[str, Any]:
    """Decide whether a run may be cited as ADR-0030 acceptance evidence.

    Refuses loudly rather than reporting a green-looking run as evidence. The SHADOW
    refusal is the one ADR-0030 §2 calls out by name.

    ``evidence_bundle`` is the harness `summary.json` for the run, when the caller has
    it. Its gate ledger is the only thing that can say whether the gates the run reports
    as absent were *excluded* (not applicable — still evidence) or *not evaluated*
    (asked for and missing — not evidence). See :mod:`evidara_cli.gate_coverage`; the
    rule is implemented there and nowhere else, so `flip_refusals` inherits it through
    ``is_acceptance_evidence`` rather than re-deriving it.

    Omitting the bundle keeps the pre-#744-split behaviour exactly: the run-level rules
    below decide alone. That is a real gap — a bundle nobody passes cannot refuse — and
    it is why the note names the bundle rather than leaving the reader to remember.
    """
    refusals: list[str] = []
    if bool(run.get("refused")):
        refusals.append(EVIDENCE_RUN_REFUSED)
    if str(run.get("status") or "").lower() != "completed":
        refusals.append(EVIDENCE_RUN_NOT_COMPLETED)
    if str(run.get("mode") or "").lower() != MODE_ACCEPTANCE:
        refusals.append(EVIDENCE_MODE_NOT_ACCEPTANCE)
    if str(execution_mode or "").lower() == "shadow":
        refusals.append(EVIDENCE_EXECUTION_MODE_SHADOW)
    count = captured_resources_count
    if count is None:
        count = run.get("captured_resources_count")
    if isinstance(count, int) and count <= 0:
        refusals.append(EVIDENCE_NO_CAPTURED_RESOURCES)

    gate_coverage = gate_coverage_verdict(evidence_bundle)
    items = [{"code": code, "detail": _EVIDENCE_DETAIL[code]} for code in refusals]
    items.extend(gate_coverage["refusals"])

    return {
        "is_acceptance_evidence": not items,
        "refusals": items,
        "run_id": run.get("run_id"),
        "mode": run.get("mode"),
        "execution_mode": execution_mode,
        "captured_resources_count": count,
        "gate_coverage": gate_coverage,
        "note": (
            "A pass here justifies only the gates that actually ran. ADR-0030 §5: a gate "
            "the operator excluded is still a defensible pass; a gate that was asked for "
            "and could not run leaves a hole and refuses the flip (#744). Cite the "
            "harness bundle with --evidence-bundle so `gate_coverage` is derived rather "
            "than assumed — without it, only the run-level rules above ran."
        ),
    }


# ---------------------------------------------------------------------------------
# Source-version lookup
# ---------------------------------------------------------------------------------


def find_source_version(versions_payload: Any, source_version_id: Any) -> dict[str, Any] | None:
    """Pick one version out of ``GET /v1/sources/{source_id}/versions``.

    There is no ``GET /v1/versions/{id}``, so everything that needs a version's
    ``execution_mode`` or provider has to resolve it through its source's list.
    """
    if not source_version_id:
        return None
    if isinstance(versions_payload, dict):
        versions = versions_payload.get("data")
    else:
        versions = versions_payload
    for version in versions or []:
        if isinstance(version, dict) and version.get("source_version_id") == source_version_id:
            return version
    return None


def version_execution_mode(version: dict[str, Any] | None) -> str | None:
    """The version's ``execution_mode`` — ``shadow`` is what disqualifies evidence."""
    if not isinstance(version, dict):
        return None
    mode = version.get("execution_mode")
    return str(mode) if mode is not None else None


# ---------------------------------------------------------------------------------
# ADR-0030 config-key flip (`enabled: true`)
# ---------------------------------------------------------------------------------
#
# **The flip guard is server-side and this module no longer mirrors it (#854).**
#
# It used to live here: `flip_refusals`, `evidence_binding_strength` and `verify_flip`
# derived the eight refusals, the binding strength and the read-back locally, and
# `coverage enable` PUT only after they passed. The admin panel, hitting the same
# endpoint, required a non-empty free-text note and nothing else — so two clients
# guarded the platform's most dangerous action by two different rules and **the easier
# path was the weaker one**. A third copy of a rule that already warns it exists twice
# was never going to hold.
#
# `PUT /v1/sources/blueprint-templates/{overlay}/{template}/enablement` now derives all
# of it: it re-derives the acceptance verdict from the cited run, binds that run to the
# template by the version's own `overlay_id`/`provider_template_id` (exact, where the
# client could only see the provider — #846), requires the two ADR-0030
# acknowledgements, and re-reads the write. Refusals come back as HTTP 409 carrying
# `refusals[].code` in the vocabulary below, which is unchanged in spelling and
# meaning; the codes are what agents branch on and the `coverage-acceptance-loop` skill
# documents.
#
# The server additionally refuses `evidence_run_not_found`,
# `evidence_run_template_mismatch`, `evidence_run_template_unbindable` and
# `no_audit_note_recorded` — all strictly additional.

#: The one refusal that stays client-side: it compares *this module's* lock derivation
#: against the server's `launchable`, which is tautological on the server that produces
#: `launchable`. `enable` is the only coverage command whose client-side derivation
#: gates a write, so unlike `templates` and `preflight` a disagreement is disqualifying.
FLIP_CLASSIFICATION_DISAGREES = "classification_disagrees_with_server"

FLIP_CLASSIFICATION_DISAGREES_DETAIL = (
    "The client-side lock derivation disagrees with the server's `launchable`. "
    "This command gates a *write* on that derivation, so a disagreement is "
    "disqualifying. Trust /v1/runs/readiness and file a bug."
)


def is_already_in_desired_state(*, template: dict[str, Any], desired_enabled: bool) -> bool:
    """Whether the flip would genuinely change nothing — provenance included.

    The effective boolean alone is not the state. ``enabled: false`` with provenance
    ``default`` is ``never_turned``, which ADR-0030's acceptance waiver still dispatches
    at; ``enabled: false`` with provenance ``override`` is an operator kill switch, which
    it does not (see :func:`config_key_state`, #768). Short-circuiting a ``--disable`` on
    the boolean alone therefore reports "already off" and installs no kill switch, and
    the operator believes they shut a portal off that is still live.

    The desired state is the *pair*: the requested value, recorded as an override.
    """
    if bool(template.get("enabled")) is not bool(desired_enabled):
        return False
    return str(template.get("source") or "default").strip().lower() == "override"


def server_refusals(payload: Any) -> list[dict[str, str]]:
    """Read `refusals` off the server's 409 body, failing closed on an unknown shape.

    A 409 whose body this cannot parse is still a refusal — it must never be reported
    as an empty refusal list, which would read as "nothing was wrong".
    """
    items = payload.get("refusals") if isinstance(payload, dict) else None
    parsed = [
        {"code": str(item.get("code")), "detail": str(item.get("detail") or "")}
        for item in (items or [])
        if isinstance(item, dict) and item.get("code")
    ]
    if parsed:
        return parsed
    detail = payload.get("detail") if isinstance(payload, dict) else None
    return [
        {
            "code": "refused_by_server",
            "detail": str(detail or "platform-control refused the flip and gave no codes."),
        }
    ]
