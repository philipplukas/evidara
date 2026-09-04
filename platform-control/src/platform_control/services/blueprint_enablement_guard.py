"""The ADR-0030 config-key flip guard — one derivation, both clients (#854, #846).

Until this module existed the platform's most dangerous action was guarded twice, by
two different rules, and **the easier path was the weaker one**:

- `evidara workflow coverage enable` (#832) required a cited acceptance run, re-derived
  the acceptance verdict, checked provider readiness, demanded an explicit
  acknowledgement to reopen an operator's kill switch, and read the write back — and
  refused with eight named codes.
- The admin panel's `BlueprintEnablementDialog` required **a non-empty free-text note**
  and nothing else. An operator refused by the CLI could get the same state by typing
  one character into a textarea, which made the CLI's guard advisory rather than
  enforced (#854).

So the guard moved here, behind `PUT /v1/sources/blueprint-templates/{overlay}/
{template}/enablement`. Both clients now consume the same refusals, and there is no
"weaker path" left to take, because there is only one path.

## Vocabulary stability

The refusal codes are a **public interface**: the `coverage-acceptance-loop` skill
documents them and agents branch on them. The eight codes #832 shipped keep their exact
spelling and meaning here. `classification_disagrees_with_server` is the one that stays
client-side — it compares the CLI's local lock derivation against the server's
`launchable`, which is tautological on the server that produces `launchable`.

Three codes are new, and all three only ever *add* a refusal:

- `evidence_run_not_found` — the cited run id resolves to nothing.
- `evidence_run_template_mismatch` — the cited run's source version records a
  *different* blueprint template (#846).
- `evidence_run_template_unbindable` — the version records no blueprint provenance and
  its acquisition spec does not equal this template's resolved spec, so the run cannot
  be bound to this template at all (#846).
- `no_audit_note_recorded` — a flip in either direction must say why.

## Why the binding is exact here and was not in the CLI

#846's finding: the cited run was bound to the template only by its **acquisition
provider**, and all 26 cantons plus Bund sit behind the single `lexfind` provider, so
one passing run for any canton satisfied the check for every LexFind template.

The issue proposed two fixes for a *client*: compare the version's `acquisition_spec`
against `POST /v1/sources/blueprint-preview`, or project `overlay_id` /
`provider_template_id` onto `SourceVersionResponse`. Server-side a third option is
available and is strictly better than both: `SourceVersion` **already carries those two
columns** (`models/source_version.py:45-46`), so the binding is read directly off the
row and is exact, with no contract expansion and no tolerance for seed overrides (#710)
needed — an override changes the spec but never the provenance columns.

The spec comparison is still implemented, as the *fallback* for a version created from a
hand-written `acquisition_spec` (those columns are NULL). Where neither binds, the guard
refuses; where it binds only by spec equality, the flip is allowed but the response
carries `needs_human: true` rather than a quiet artifact field.
"""

from __future__ import annotations

from dataclasses import dataclass, field
from typing import Any

# --- ADR-0030 code key (provider readiness) --------------------------------------
READINESS_SCAFFOLD = "scaffold"
READINESS_AWAITING_EVIDENCE = "awaiting_evidence"
READINESS_LIVE = "live"

MODE_ACCEPTANCE = "acceptance"
EXECUTION_MODE_SHADOW = "shadow"
RUN_STATUS_COMPLETED = "completed"

# --- Acceptance-evidence refusals (`evidara_cli.coverage` spellings) --------------
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
    EVIDENCE_RUN_NOT_COMPLETED: "Only a completed run can serve as acceptance evidence.",
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

# --- Flip refusals (`evidara_cli.coverage` spellings; three additions) ------------
FLIP_NO_EVIDENCE_RUN = "no_evidence_run_cited"
FLIP_EVIDENCE_RUN_NOT_FOUND = "evidence_run_not_found"
FLIP_EVIDENCE_NOT_ACCEPTANCE = "evidence_run_is_not_acceptance_evidence"
FLIP_EVIDENCE_PROVIDER_UNRESOLVED = "evidence_run_provider_unresolved"
FLIP_PROVIDER_MISMATCH = "evidence_run_provider_mismatch"
FLIP_EVIDENCE_CAPTURE_COUNT_UNKNOWN = "evidence_run_capture_count_unknown"
FLIP_TEMPLATE_MISMATCH = "evidence_run_template_mismatch"
FLIP_TEMPLATE_UNBINDABLE = "evidence_run_template_unbindable"
FLIP_PROVIDER_NOT_LIVE = "provider_not_live_not_acknowledged"
FLIP_KILL_SWITCH_NOT_ACKNOWLEDGED = "operator_kill_switch_not_acknowledged"
FLIP_NO_AUDIT_NOTE = "no_audit_note_recorded"

_FLIP_DETAIL = {
    FLIP_NO_EVIDENCE_RUN: (
        "ADR-0030 §5: the config key is turned *after* acceptance-run evidence is "
        "captured, not on confidence. Cite the run in `evidence_run_id` (CLI: "
        "--evidence-run-id)."
    ),
    FLIP_EVIDENCE_RUN_NOT_FOUND: (
        "No run exists with the cited id, so nothing was re-derived. Refused rather "
        "than skipped-and-passed (#744)."
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
    FLIP_TEMPLATE_MISMATCH: (
        "The cited run's source version was created from a DIFFERENT blueprint "
        "template. A same-provider run is not evidence for this template: all 26 "
        "cantons and Bund sit behind the single `lexfind` provider, so provider-level "
        "agreement would enable every one of them off one canton's run (#846)."
    ),
    FLIP_TEMPLATE_UNBINDABLE: (
        "The cited run's source version records no blueprint provenance and its "
        "acquisition spec is not this template's, so the run cannot be bound to this "
        "template. Cite a run whose version was created from this template (#846)."
    ),
    FLIP_PROVIDER_NOT_LIVE: (
        "ADR-0030 §2: a template may only be `enabled: true` if its provider is LIVE — "
        "not merely AWAITING_EVIDENCE, because an enabled template would dispatch "
        "production runs on evidence nobody captured. That invariant is asserted over "
        "`source_blueprints.yaml` by test_blueprint_provider_parity.py but NOT over the "
        "override table this writes, so the ordering is on you: move the code key "
        "first. Set `acknowledge_provider_below_live` (CLI: "
        "--acknowledge-provider-below-live) to arm the key ahead of it anyway."
    ),
    FLIP_KILL_SWITCH_NOT_ACKNOWLEDGED: (
        "This key was turned off by an operator — a deliberate kill switch, not a key "
        "that was never earned. Acceptance evidence does not waive it. Set "
        "`reopen_operator_kill_switch` (CLI: --reopen-operator-kill-switch) only after "
        "asking them."
    ),
    FLIP_NO_AUDIT_NOTE: (
        "Record why the key is moving. The note is the only durable record of why this "
        "template was trusted — or why a portal was shut off — and a flip with no "
        "recorded reason is indistinguishable from one made by guessing."
    ),
}

# --- Read-back problems (`evidara_cli.coverage` spellings) ------------------------
FLIP_READ_BACK_DISAGREES = "read_back_disagrees"
FLIP_NO_OVERRIDE_RECORDED = "no_override_recorded"

_VERIFY_DETAIL = {
    FLIP_READ_BACK_DISAGREES: (
        "The write returned but the blueprint-template read model still reports the old "
        "effective key. The key was NOT flipped — do not report it as flipped."
    ),
    FLIP_NO_OVERRIDE_RECORDED: (
        "The effective key is what was asked for, but the read model still attributes "
        "it to the shipped default rather than an operator override. `set_enabled` "
        "always writes an override row, so the write did not land and the value merely "
        "happens to agree."
    ),
}

# --- Evidence binding strength ----------------------------------------------------
#: The run's source version records exactly this overlay + provider template. Exact.
BINDING_TEMPLATE = "template"
#: No blueprint provenance on the version, but its acquisition spec equals this
#: template's resolved spec. Near-exact — a human should confirm.
BINDING_ACQUISITION_SPEC = "acquisition_spec"
#: Only the acquisition provider agrees. Too weak to enable on (#846).
BINDING_PROVIDER = "provider"
#: Nothing ties the run to this template.
BINDING_NONE = "none"


@dataclass(frozen=True)
class Refusal:
    code: str
    detail: str


def _refusals(codes: list[str], table: dict[str, str]) -> list[Refusal]:
    return [Refusal(code=code, detail=table[code]) for code in codes]


# ---------------------------------------------------------------------------------
# Acceptance-evidence verdict
# ---------------------------------------------------------------------------------


@dataclass(frozen=True)
class AcceptanceVerdict:
    is_acceptance_evidence: bool
    refusals: list[Refusal]
    run_id: str | None
    mode: str | None
    execution_mode: str | None
    captured_resources_count: int | None


def acceptance_evidence_verdict(
    *,
    run_id: str | None,
    refused: bool,
    status: str | None,
    mode: str | None,
    execution_mode: str | None,
    captured_resources_count: int | None,
) -> AcceptanceVerdict:
    """Decide whether a run may be cited as ADR-0030 acceptance evidence.

    Mirrors ``evidara_cli.coverage.acceptance_evidence_verdict`` exactly, including the
    SHADOW refusal ADR-0030 §2 calls out by name. Every check refuses loudly rather than
    reporting a green-looking run as evidence.

    ``captured_resources_count`` is typed optional because a check that cannot run must
    refuse rather than pass (#744). The ORM column is a non-nullable int, so the
    ``None`` branch is unreachable from the router today — it is kept live and tested so
    that a future read model which *can* omit the count fails closed instead of
    silently skipping the check.
    """
    codes: list[str] = []
    if refused:
        codes.append(EVIDENCE_RUN_REFUSED)
    if str(status or "").strip().lower() != RUN_STATUS_COMPLETED:
        codes.append(EVIDENCE_RUN_NOT_COMPLETED)
    if str(mode or "").strip().lower() != MODE_ACCEPTANCE:
        codes.append(EVIDENCE_MODE_NOT_ACCEPTANCE)
    if str(execution_mode or "").strip().lower() == EXECUTION_MODE_SHADOW:
        codes.append(EVIDENCE_EXECUTION_MODE_SHADOW)
    if isinstance(captured_resources_count, int) and captured_resources_count <= 0:
        codes.append(EVIDENCE_NO_CAPTURED_RESOURCES)

    return AcceptanceVerdict(
        is_acceptance_evidence=not codes,
        refusals=_refusals(codes, _EVIDENCE_DETAIL),
        run_id=run_id,
        mode=mode,
        execution_mode=execution_mode,
        captured_resources_count=captured_resources_count,
    )


# ---------------------------------------------------------------------------------
# Evidence binding (#846)
# ---------------------------------------------------------------------------------


@dataclass(frozen=True)
class EvidenceBinding:
    """How tightly the cited run is bound to *this* template, and why not tighter."""

    strength: str
    #: The refusal this binding earns, if it is too weak to enable on.
    refusal_code: str | None = None
    bound_overlay_id: str | None = None
    bound_provider_template_id: str | None = None

    @property
    def is_template_exact(self) -> bool:
        return self.strength == BINDING_TEMPLATE


def _normalise_spec(spec: Any) -> dict[str, Any] | None:
    """Re-parse a spec through the discriminated union so both sides carry defaults.

    A persisted spec is whatever ``model_dump(mode="json")`` produced when the version
    was created; a freshly resolved template spec carries today's defaults. Round-
    tripping both through the same model is what makes the comparison about the fields
    that identify a portal rather than about which defaults existed when.
    """
    if not isinstance(spec, dict):
        return None
    # Imported lazily: `schemas.source` is a heavy module and this keeps the guard's
    # pure verdict functions importable without it.
    from platform_control.schemas.source import parse_acquisition_spec

    try:
        return parse_acquisition_spec(spec).model_dump(mode="json")
    except Exception:
        # An unparseable spec cannot be compared, so it cannot bind. Fail closed.
        return None


def evidence_binding(
    *,
    template_overlay_id: str,
    template_provider_template_id: str,
    template_provider: str | None,
    template_spec: Any,
    version_overlay_id: str | None,
    version_provider_template_id: str | None,
    version_spec: Any,
) -> EvidenceBinding:
    """Bind the cited run's source version to the template whose key is being flipped.

    Ordered strongest-first. The provenance columns are exact and immune to operator
    seed overrides (#710), which change a spec but never the columns; the spec
    comparison is the fallback for a version created from a hand-written spec, where
    those columns are NULL.
    """
    version_provider = None
    if isinstance(version_spec, dict):
        raw_provider = version_spec.get("provider")
        version_provider = str(raw_provider) if raw_provider is not None else None

    if not version_provider:
        return EvidenceBinding(
            strength=BINDING_NONE, refusal_code=FLIP_EVIDENCE_PROVIDER_UNRESOLVED
        )
    if template_provider and version_provider != str(template_provider):
        return EvidenceBinding(strength=BINDING_NONE, refusal_code=FLIP_PROVIDER_MISMATCH)

    if version_overlay_id and version_provider_template_id:
        if (
            version_overlay_id == template_overlay_id
            and version_provider_template_id == template_provider_template_id
        ):
            return EvidenceBinding(
                strength=BINDING_TEMPLATE,
                bound_overlay_id=version_overlay_id,
                bound_provider_template_id=version_provider_template_id,
            )
        return EvidenceBinding(
            strength=BINDING_PROVIDER,
            refusal_code=FLIP_TEMPLATE_MISMATCH,
            bound_overlay_id=version_overlay_id,
            bound_provider_template_id=version_provider_template_id,
        )

    normalised_version = _normalise_spec(version_spec)
    normalised_template = _normalise_spec(template_spec)
    if (
        normalised_version is not None
        and normalised_template is not None
        and normalised_version == normalised_template
    ):
        return EvidenceBinding(strength=BINDING_ACQUISITION_SPEC)
    return EvidenceBinding(strength=BINDING_PROVIDER, refusal_code=FLIP_TEMPLATE_UNBINDABLE)


# ---------------------------------------------------------------------------------
# The flip verdict
# ---------------------------------------------------------------------------------


@dataclass(frozen=True)
class FlipVerdict:
    refusals: list[Refusal] = field(default_factory=list)
    needs_human: bool = False
    #: Why a human is still wanted even when nothing refused.
    needs_human_reasons: list[str] = field(default_factory=list)

    @property
    def refused(self) -> bool:
        return bool(self.refusals)


def flip_verdict(
    *,
    desired_enabled: bool,
    note: str | None,
    readiness: str,
    config_key_provenance: str,
    evidence_run_id: str | None,
    evidence_run_exists: bool,
    acceptance: AcceptanceVerdict | None,
    binding: EvidenceBinding | None,
    reopen_operator_kill_switch: bool,
    acknowledge_provider_below_live: bool,
) -> FlipVerdict:
    """Every reason the ADR-0030 config key must not move to ``desired_enabled``.

    Turning the key **off** is a kill switch and needs no evidence — it is always the
    safe direction — but it does need an audit note. Turning it **on** needs a cited run
    that survives the acceptance verdict, binds to *this* template, and both ADR-0030
    ordering rules acknowledged where they are not met.

    Every check keys off the *states* (``readiness``, ``config_key_provenance``), never
    off a single priority-ordered "blocker" value. Keying the kill-switch check off a
    blocker is what let a scaffold provider mask a closed key and flip it
    unacknowledged.
    """
    codes: list[str] = []
    reasons: list[str] = []

    if not str(note or "").strip():
        codes.append(FLIP_NO_AUDIT_NOTE)

    if not desired_enabled:
        # Closing the key needs nothing else: it can only ever reduce what dispatches.
        return FlipVerdict(refusals=_refusals(codes, _FLIP_DETAIL))

    if not evidence_run_id:
        codes.append(FLIP_NO_EVIDENCE_RUN)
    elif not evidence_run_exists:
        codes.append(FLIP_EVIDENCE_RUN_NOT_FOUND)
    else:
        if acceptance is None or not acceptance.is_acceptance_evidence:
            codes.append(FLIP_EVIDENCE_NOT_ACCEPTANCE)
        if acceptance is not None and acceptance.captured_resources_count is None:
            codes.append(FLIP_EVIDENCE_CAPTURE_COUNT_UNKNOWN)
        if binding is None:
            codes.append(FLIP_EVIDENCE_PROVIDER_UNRESOLVED)
        elif binding.refusal_code is not None:
            codes.append(binding.refusal_code)
        elif not binding.is_template_exact:
            reasons.append(
                "The cited run binds to this template by acquisition-spec equality, not "
                "by recorded blueprint provenance. Confirm by hand that the run is this "
                "template's (#846)."
            )

    if readiness != READINESS_LIVE and not acknowledge_provider_below_live:
        codes.append(FLIP_PROVIDER_NOT_LIVE)
    elif readiness != READINESS_LIVE:
        reasons.append(
            f"The config key is being armed ahead of the code key, which is still "
            f"'{readiness}'. ADR-0030 §2 wants LIVE first; harm is deferred, not absent."
        )

    if config_key_provenance == "override" and not reopen_operator_kill_switch:
        codes.append(FLIP_KILL_SWITCH_NOT_ACKNOWLEDGED)
    elif config_key_provenance == "override":
        reasons.append(
            "An operator's deliberate kill switch is being reopened. Confirm they agreed."
        )

    return FlipVerdict(
        refusals=_refusals(codes, _FLIP_DETAIL),
        needs_human=bool(reasons),
        needs_human_reasons=reasons,
    )


def read_back_problems(
    *, effective_enabled: bool, provenance: str, desired_enabled: bool
) -> list[Refusal]:
    """Prove the flip landed by re-reading the template, not by trusting the write.

    Both conditions must hold: the effective key is what was asked for, **and** the read
    model attributes it to an operator override. Either alone is also satisfied by a
    write that silently did nothing — the failure mode behind #631 and #713.
    """
    codes: list[str] = []
    if bool(effective_enabled) is not bool(desired_enabled):
        codes.append(FLIP_READ_BACK_DISAGREES)
    if str(provenance or "default").strip().lower() != "override":
        codes.append(FLIP_NO_OVERRIDE_RECORDED)
    return _refusals(codes, _VERIFY_DETAIL)
