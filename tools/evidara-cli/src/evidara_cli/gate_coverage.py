"""Why an acceptance gate is absent — and which absences disqualify the evidence.

`checks.skipped_gates` in a harness bundle answers *which* gates did not run. It has
never answered **why**, and the two reasons mean opposite things:

- The operator did not ask for the gate — the template declares no title pattern, no
  language to assert. The gate is **excluded**: not applicable, and a run without it is
  still defensible acceptance evidence.
- The gate was asked for and could not run — legal-search was not reachable, the
  projection never became queryable, there were no processed documents to assert over.
  The gate is **not evaluated**: a hole in the evidence, and reporting the run as a pass
  is the green-over-nothing failure this repo keeps paying for (#605, #675, #713, #728).

One list cannot carry both, so #744's `skipped_gates` rendered an unreachable
legal-search as "not applicable to this template".

## The vocabulary is borrowed, not invented

Soda Core v4 splits exactly this pair — `CheckOutcome.EXCLUDED` (deselected by a
selector) versus `NOT_EVALUATED` (unsupported by the data source, an upstream query
failed, a threshold evaluated to `None`) — and escalates only the second to a
contract-level error and a non-zero exit, because *"exiting 0 would leave it
under-asserting silently."* Its names are used here verbatim. (Soda Core v4 is Elastic
License 2.0; the design is readable, the code is not shippable here.)

Two neighbours were considered and rejected as the primary vocabulary:

- **OpenLineage's `TestRunFacet`** publishes `pass|fail|skip`. `skip` is one bucket for
  both reasons, so it is the shape we already have. It is still the right *interchange*
  target (Apache-2.0, LF AI & Data graduate); an excluded gate maps to `skip`, and a
  not-evaluated one to `skip` plus `severity: error`.
- **dbt's `skipped`** means only "not run because the DAG upstream failed"
  (`SkippedUpstreamFailed` in the v2 enum) — narrower than either of ours.

## The escalation rule lives here and nowhere else

`gate_coverage_verdict()` is the only implementation of "any not-evaluated gate means
this is not acceptance evidence". `coverage.acceptance_evidence_verdict()` folds its
refusals in, and `coverage.flip_refusals()` therefore refuses the `enabled: true` write
through the existing `evidence_run_is_not_acceptance_evidence` code. No consumer
re-derives it.

## Legacy bundles are read conservatively, not migrated

A bundle that carries `skipped_gates` but no `gate_coverage` predates the split, so the
reason for each entry is unrecoverable from the file. Every such entry is read as
**not evaluated** — the safe direction: it can only refuse evidence that might have been
fine, never accept evidence that is not. This costs nothing on the bundles that exist:
all five persisted `skipped_gates` lists under `docs/runbooks/evidence/` are empty, and
an empty list means the same thing under both readings.
"""

from __future__ import annotations

import json
from pathlib import Path
from typing import Any

# --- Outcomes (Soda Core v4 `CheckOutcome`) --------------------------------------
GATE_EXCLUDED = "excluded"
GATE_NOT_EVALUATED = "not_evaluated"

# --- Reasons the harnesses emit ---------------------------------------------------
REASON_NOT_RECORDED = "reason_not_recorded"

# --- Refusal codes ----------------------------------------------------------------
EVIDENCE_GATE_NOT_EVALUATED = "gate_not_evaluated"
EVIDENCE_GATE_COVERAGE_UNKNOWN = "gate_coverage_unknown"

_GATE_DETAIL = {
    EVIDENCE_GATE_NOT_EVALUATED: (
        "One or more gates were asked for and could not run, so what they would have "
        "asserted is unknown. An unverified gate is not a passed gate (#744): the run "
        "may not be cited as ADR-0030 acceptance evidence until they run. Deliberately "
        "excluded gates do not trigger this — only gates that were wanted and missing."
    ),
    EVIDENCE_GATE_COVERAGE_UNKNOWN: (
        "The bundle reports no gate coverage at all (no `checks.gate_coverage`, no "
        "`checks.skipped_gates`), so which gates ran cannot be established from it. "
        "Treated as unverified rather than as full coverage."
    ),
}


def load_evidence_bundle(path: str | Path) -> dict[str, Any]:
    """Read a harness `summary.json` from disk.

    Raises rather than returning an empty bundle: an unreadable bundle read as "no
    gates skipped" would be the exact failure this module exists to prevent.
    """
    raw = Path(path).read_text(encoding="utf-8")
    bundle = json.loads(raw)
    if not isinstance(bundle, dict):
        raise ValueError(f"{path}: evidence bundle must be a JSON object")
    return bundle


def _entries(checks: dict[str, Any]) -> tuple[list[dict[str, str]], str]:
    """Normalise a bundle's gate ledger to `[{gate, outcome, reason}]` plus its shape."""
    ledger = checks.get("gate_coverage")
    if isinstance(ledger, list):
        normalised: list[dict[str, str]] = []
        for item in ledger:
            if not isinstance(item, dict):
                continue
            gate = str(item.get("gate") or "")
            if not gate:
                continue
            outcome = str(item.get("outcome") or "")
            # An unrecognised outcome is not silently trusted: anything that is not
            # explicitly `excluded` is read as not-evaluated.
            if outcome != GATE_EXCLUDED:
                outcome = GATE_NOT_EVALUATED
            normalised.append(
                {
                    "gate": gate,
                    "outcome": outcome,
                    "reason": str(item.get("reason") or REASON_NOT_RECORDED),
                }
            )
        return normalised, "gate_coverage"

    legacy = checks.get("skipped_gates")
    if isinstance(legacy, list):
        return (
            [
                {
                    "gate": str(gate),
                    "outcome": GATE_NOT_EVALUATED,
                    "reason": REASON_NOT_RECORDED,
                }
                for gate in legacy
                if str(gate)
            ],
            "legacy_skipped_gates",
        )

    return [], "absent"


def gate_coverage_verdict(bundle: dict[str, Any] | None) -> dict[str, Any]:
    """Split a harness bundle's absent gates, and say whether the run still evidences.

    ``bundle`` is a parsed harness `summary.json`. Passing ``None`` means no bundle was
    cited at all, which reports ``reported: False`` and refuses nothing — the caller
    decides whether a missing bundle is acceptable. Passing a bundle that reports no
    coverage *does* refuse: the file exists and is silent about what ran.
    """
    if bundle is None:
        return {
            "reported": False,
            "source_shape": None,
            "excluded": [],
            "not_evaluated": [],
            "is_acceptance_evidence": True,
            "refusals": [],
        }

    checks = bundle.get("checks")
    checks = checks if isinstance(checks, dict) else {}
    entries, shape = _entries(checks)

    excluded = [e for e in entries if e["outcome"] == GATE_EXCLUDED]
    not_evaluated = [e for e in entries if e["outcome"] == GATE_NOT_EVALUATED]

    codes: list[str] = []
    if shape == "absent":
        codes.append(EVIDENCE_GATE_COVERAGE_UNKNOWN)
    if not_evaluated:
        codes.append(EVIDENCE_GATE_NOT_EVALUATED)

    def detail(code: str) -> str:
        # "some gate did not run" is not actionable, so the refusal names each gate and
        # the reason it could not run rather than leaving the operator to go find them.
        if code != EVIDENCE_GATE_NOT_EVALUATED:
            return _GATE_DETAIL[code]
        named = ", ".join(f"{e['gate']} ({e['reason']})" for e in not_evaluated)
        return f"{_GATE_DETAIL[code]} Not evaluated: {named}."

    return {
        "reported": shape != "absent",
        "source_shape": shape,
        "excluded": excluded,
        "not_evaluated": not_evaluated,
        "is_acceptance_evidence": not codes,
        "refusals": [{"code": code, "detail": detail(code)} for code in codes],
    }
