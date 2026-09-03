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
) -> dict[str, Any]:
    """Decide whether a run may be cited as ADR-0030 acceptance evidence.

    Refuses loudly rather than reporting a green-looking run as evidence. The SHADOW
    refusal is the one ADR-0030 §2 calls out by name.
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

    return {
        "is_acceptance_evidence": not refusals,
        "refusals": [{"code": code, "detail": _EVIDENCE_DETAIL[code]} for code in refusals],
        "run_id": run.get("run_id"),
        "mode": run.get("mode"),
        "execution_mode": execution_mode,
        "captured_resources_count": count,
        "note": (
            "A pass here justifies only the gates that actually ran. ADR-0030 §5: read the "
            "harness's Gate coverage / skipped_gates before flipping `enabled: true`, and "
            "treat a skipped gate as unverified, not as verified-and-green (#744)."
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


def version_provider(version: dict[str, Any] | None) -> str | None:
    """The acquisition provider the version actually ran.

    ``SourceVersionResponse`` does not expose ``overlay_id`` / ``provider_template_id``
    even though the ORM model carries both
    (``platform_control/schemas/source.py:460-471`` vs ``run_service.py:210-229``), so
    the provider on the acquisition spec is the *only* binding between a run and the
    blueprint template it came from that the API makes visible. It is provider-level,
    not template-level — see :func:`evidence_binding_strength`.
    """
    if not isinstance(version, dict):
        return None
    spec = version.get("acquisition_spec")
    if not isinstance(spec, dict):
        return None
    provider = spec.get("provider")
    return str(provider) if provider is not None else None


# ---------------------------------------------------------------------------------
# ADR-0030 config-key flip (`enabled: true`)
# ---------------------------------------------------------------------------------

FLIP_NO_EVIDENCE_RUN = "no_evidence_run_cited"
FLIP_EVIDENCE_NOT_ACCEPTANCE = "evidence_run_is_not_acceptance_evidence"
FLIP_EVIDENCE_PROVIDER_UNRESOLVED = "evidence_run_provider_unresolved"
FLIP_PROVIDER_MISMATCH = "evidence_run_provider_mismatch"
FLIP_EVIDENCE_CAPTURE_COUNT_UNKNOWN = "evidence_run_capture_count_unknown"
FLIP_CLASSIFICATION_DISAGREES = "classification_disagrees_with_server"
FLIP_PROVIDER_NOT_LIVE = "provider_not_live_not_acknowledged"
FLIP_KILL_SWITCH_NOT_ACKNOWLEDGED = "operator_kill_switch_not_acknowledged"

_FLIP_DETAIL = {
    FLIP_NO_EVIDENCE_RUN: (
        "ADR-0030 §5: the config key is turned *after* acceptance-run evidence is "
        "captured, not on confidence. Cite the run with --evidence-run-id."
    ),
    FLIP_EVIDENCE_NOT_ACCEPTANCE: (
        "The cited run cannot serve as acceptance evidence. Read "
        "`acceptance_verdict.refusals` for which rule it broke — "
        "`execution_mode_shadow` is the one that looks greenest and proves least."
    ),
    FLIP_EVIDENCE_PROVIDER_UNRESOLVED: (
        "The cited run's acquisition provider could not be resolved, so the evidence "
        "cannot be tied to this template at all. Refused rather than skipped-and-passed "
        "(#744)."
    ),
    FLIP_PROVIDER_MISMATCH: (
        "The cited run ran a different acquisition provider than this template uses. "
        "Evidence about one portal is not evidence about another (ADR-0030 §2)."
    ),
    FLIP_EVIDENCE_CAPTURE_COUNT_UNKNOWN: (
        "The cited run reports no `captured_resources_count`, so the 'it captured "
        "something' check did not run. A check that cannot run must refuse, not pass "
        "(#744)."
    ),
    FLIP_CLASSIFICATION_DISAGREES: (
        "The client-side lock derivation disagrees with the server's `launchable`. "
        "This command gates a *write* on that derivation, so a disagreement is "
        "disqualifying. Trust /v1/runs/readiness and file a bug."
    ),
    FLIP_PROVIDER_NOT_LIVE: (
        "ADR-0030 §2: a template may only be `enabled: true` if its provider is LIVE — "
        "not merely AWAITING_EVIDENCE, because an enabled template would dispatch "
        "production runs on evidence nobody captured. That invariant is asserted over "
        "`source_blueprints.yaml` by test_blueprint_provider_parity.py but NOT over the "
        "override table this writes, so the ordering is on you: move the code key "
        "first. Pass --acknowledge-provider-below-live to arm the key ahead of it "
        "anyway."
    ),
    FLIP_KILL_SWITCH_NOT_ACKNOWLEDGED: (
        "This key was turned off by an operator — a deliberate kill switch, not a key "
        "that was never earned. Acceptance evidence does not waive it. Pass "
        "--reopen-operator-kill-switch only after asking them."
    ),
}


def flip_refusals(
    *,
    template: dict[str, Any],
    desired_enabled: bool,
    evidence_verdict: dict[str, Any] | None = None,
    evidence_provider: str | None = None,
    reopen_acknowledged: bool = False,
    below_live_acknowledged: bool = False,
) -> list[dict[str, str]]:
    """Reasons the ADR-0030 config key must not be flipped to ``desired_enabled``.

    ``template`` is a :func:`classify_template` verdict. Turning the key **off** is a
    kill switch and needs no evidence; turning it **on** needs a run that survives
    :func:`acceptance_evidence_verdict`, a provider that matches, and both ADR-0030
    ordering rules acknowledged where they are not met.

    Every check here keys off ``config_key`` / ``code_key`` — the *states* — never off
    ``blocker``, which is a single priority-ordered value. Keying the kill-switch check
    off ``blocker`` is what let a scaffold provider mask a closed key and flip it
    unacknowledged: ``classify_template`` reports ``provider_scaffold`` for that
    template and the closed key never surfaces.
    """
    if not desired_enabled:
        return []

    codes: list[str] = []
    if evidence_verdict is None:
        codes.append(FLIP_NO_EVIDENCE_RUN)
    else:
        if not evidence_verdict.get("is_acceptance_evidence"):
            codes.append(FLIP_EVIDENCE_NOT_ACCEPTANCE)
        if evidence_verdict.get("captured_resources_count") is None:
            codes.append(FLIP_EVIDENCE_CAPTURE_COUNT_UNKNOWN)
        template_provider = template.get("provider")
        if not evidence_provider:
            codes.append(FLIP_EVIDENCE_PROVIDER_UNRESOLVED)
        elif template_provider and str(evidence_provider) != str(template_provider):
            codes.append(FLIP_PROVIDER_MISMATCH)

    # `enable` is the only coverage command whose client-side derivation gates a write,
    # so unlike `templates` and `preflight` a disagreement here is disqualifying.
    if template.get("agrees_with_server") is False:
        codes.append(FLIP_CLASSIFICATION_DISAGREES)

    if template.get("code_key") != READINESS_LIVE and not below_live_acknowledged:
        codes.append(FLIP_PROVIDER_NOT_LIVE)

    if template.get("config_key") == CONFIG_KEY_CLOSED_BY_OPERATOR and not reopen_acknowledged:
        codes.append(FLIP_KILL_SWITCH_NOT_ACKNOWLEDGED)

    return [{"code": code, "detail": _FLIP_DETAIL[code]} for code in codes]


def evidence_binding_strength(*, evidence_provider: str | None, template: dict[str, Any]) -> str:
    """How tightly the cited run is bound to *this* template.

    ``provider`` is the strongest answer available today, and it is **weak**: all 26
    cantons and Bund sit behind the single ``lexfind`` provider, so one passing run for
    any canton satisfies this check for every LexFind template — the exact source this
    was built to serve. Treat it as a prompt to confirm the run by hand, not as a floor.
    Binding a run to its template needs ``overlay_id`` / ``provider_template_id`` on
    ``SourceVersionResponse``; comparing the version's ``acquisition_spec`` against
    ``POST /v1/sources/blueprint-preview`` would get near-template-exact with no
    platform-control change (#846).
    """
    template_provider = template.get("provider")
    if not evidence_provider or not template_provider:
        return "none"
    if str(evidence_provider) != str(template_provider):
        return "none"
    return "provider"


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


FLIP_READ_BACK_DISAGREES = "read_back_disagrees"
FLIP_NO_OVERRIDE_RECORDED = "no_override_recorded"

_FLIP_VERIFY_DETAIL = {
    FLIP_READ_BACK_DISAGREES: (
        "The PUT returned 200 but the blueprint-template read model still reports the "
        "old effective key. The key was NOT flipped — do not report it as flipped."
    ),
    FLIP_NO_OVERRIDE_RECORDED: (
        "The effective key is what was asked for, but the read model still attributes "
        "it to the shipped default rather than an operator override. `set_enabled` "
        "always writes an override row, so the write did not land and the value merely "
        "happens to agree."
    ),
}


def verify_flip(*, after_template: dict[str, Any], desired_enabled: bool) -> dict[str, Any]:
    """Prove the flip landed by re-reading the template, not by trusting the 200.

    Both conditions must hold: the effective key is what was asked for, **and** the read
    model attributes it to an operator override. Either alone is also satisfied by a
    write that silently did nothing — the failure mode behind #631 and #713.
    """
    effective = bool(after_template.get("enabled"))
    provenance = str(after_template.get("source") or "default").strip().lower()
    codes: list[str] = []
    if effective is not bool(desired_enabled):
        codes.append(FLIP_READ_BACK_DISAGREES)
    if provenance != "override":
        codes.append(FLIP_NO_OVERRIDE_RECORDED)
    return {
        "applied": not codes,
        "effective_enabled": effective,
        "provenance": provenance,
        "problems": [{"code": code, "detail": _FLIP_VERIFY_DETAIL[code]} for code in codes],
        "updated_by": after_template.get("updated_by"),
        "updated_at": after_template.get("updated_at"),
        "note": after_template.get("note"),
    }
