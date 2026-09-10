"""Retract a canonical document from Delta, with a ledger and guardrails (ADR-0057, #806).

This is the *canonical* half of the pair whose derived half is
``document_intelligence_projection_reconcile``:

- **reconcile** removes an indexed document that canonical no longer backs. It cannot help
  with a duplicate that still *has* a canonical row — such a row is not an orphan, and the
  backfill re-projects it on every rebuild.
- **this job** removes the canonical row, so reconcile can then do its job.

Run them in that order. Nothing here talks to OpenSearch: ADR-0005 makes the index a
derived view, so the correct sequence is retract truth, then re-derive the view.

Safety properties, because this is the only job in the repo that removes canonical truth:

- **Dry run by default.** Mutating requires an explicit ``--retract``; without it the job
  prints the resolved plan (rows, revisions, titles) and exits.
- **Ledger before delete.** Each removal appends to ``canonical_retractions`` first,
  carrying the reason, the operator and the Delta version to restore to. If the ledger
  append fails, nothing is deleted.
- **A closed reason vocabulary, and a mandatory narrative.** ``--reason-code`` must be a
  known code and ``--reason`` must be non-empty.
- **A duplicate may only be retracted against a survivor.** ``--reason-code
  duplicate_identity`` requires ``--superseded-by``, and the job verifies that document
  still has a canonical row before removing anything.
- **Refuses an implausibly large retraction** — more than ``--max-retraction-fraction``
  of the corpus (default 0.10, an order of magnitude tighter than reconcile's 0.25,
  because this removes truth rather than a rebuildable projection).
- **Idempotent.** A document canonical no longer has is reported as ``not_found`` and the
  run succeeds, so a repeated or resumed retraction converges instead of erroring.
- **Undoable.** No ``VACUUM`` is ever issued, so the pre-retraction Delta version stays
  readable and ``DeltaTable.restore(version_before)`` rolls the removal back.

See ``docs/runbooks/projection-reindex-backfill.md`` for the operator procedure.
"""

from __future__ import annotations

import argparse
import json
import logging
import sys
from typing import Any

from document_intelligence.config.runtime import RuntimeSettings
from document_intelligence.errors import ProcessingError
from document_intelligence.persist.retraction import (
    DEFAULT_MAX_RETRACTION_FRACTION,
    RETRACTION_REASON_CODES,
    DeltaCanonicalRetractor,
    RetractionSummary,
    check_retraction_guardrails,
)
from document_intelligence.persist.sinks import delta_storage_options

LOGGER = logging.getLogger("document_intelligence.canonical_retract")


def retractor_from_settings(settings: RuntimeSettings) -> DeltaCanonicalRetractor:
    """Build a retractor from the configured canonical surfaces."""
    if settings.surface_uris is None:
        raise ProcessingError(
            "missing_surface_config",
            "canonical retraction requires DI_SURFACES_ROOT_URI (or explicit DI_PUBLISHED_*_URI)",
        )
    retractions_uri = settings.surface_uris.canonical_retractions_uri
    if not retractions_uri:
        raise ProcessingError(
            "missing_retraction_ledger_config",
            "canonical retraction requires DI_CANONICAL_RETRACTIONS_URI when surfaces are "
            "configured per-URI; set DI_SURFACES_ROOT_URI to derive it",
        )
    return DeltaCanonicalRetractor(
        settings.surface_uris.published_documents_uri,
        settings.surface_uris.published_sections_uri,
        retractions_uri,
        storage_options=delta_storage_options(),
    )


def _parse_args(argv: list[str] | None = None) -> argparse.Namespace:
    parser = argparse.ArgumentParser(
        prog="document_intelligence_canonical_retract",
        description=(
            "Retract canonical published_documents / published_sections rows, recording each "
            "removal in the canonical_retractions ledger (ADR-0057). Dry-run unless --retract."
        ),
    )
    parser.add_argument(
        "document_ids",
        nargs="+",
        help="Canonical document_id(s) to retract (doc_<26 crockford chars>).",
    )
    parser.add_argument(
        "--reason-code",
        required=True,
        choices=sorted(RETRACTION_REASON_CODES),
        help="; ".join(f"{code}: {description}" for code, description in sorted(RETRACTION_REASON_CODES.items())),
    )
    parser.add_argument(
        "--reason",
        required=True,
        help="Narrative recorded in the ledger: why these rows are not canonical truth.",
    )
    parser.add_argument(
        "--retracted-by",
        required=True,
        help="Operator attribution recorded in the ledger (ADR-0038).",
    )
    parser.add_argument(
        "--superseded-by",
        default=None,
        help=(
            "The surviving document_id this row duplicates. Required for "
            "--reason-code duplicate_identity, and verified to exist in canonical."
        ),
    )
    parser.add_argument(
        "--retract",
        action="store_true",
        help=(
            "ACTUALLY REMOVE the canonical rows. Without this the job resolves and prints the "
            "plan only. The search index is NOT updated — run "
            "document_intelligence_projection_reconcile afterwards."
        ),
    )
    parser.add_argument(
        "--max-retraction-fraction",
        type=float,
        default=DEFAULT_MAX_RETRACTION_FRACTION,
        help=(
            "Refuse when the retraction covers more than this fraction of canonical documents "
            f"(default {DEFAULT_MAX_RETRACTION_FRACTION}). A large diff usually means the "
            "canonical side is misconfigured, not that the corpus is wrong."
        ),
    )
    return parser.parse_args(argv)


def main(argv: list[str] | None = None) -> int:
    args = _parse_args(argv)
    logging.basicConfig(level=logging.INFO, format="%(asctime)s %(levelname)s %(message)s")

    try:
        retractor = retractor_from_settings(RuntimeSettings.from_environment())
        plan = retractor.plan(
            args.document_ids,
            reason_code=args.reason_code,
            reason=args.reason,
            retracted_by=args.retracted_by,
            superseded_by_document_id=args.superseded_by,
        )
    except Exception as exc:
        LOGGER.exception("canonical retraction planning failed")
        print(json.dumps({"status": "failed", "error": str(exc)}, indent=2), file=sys.stderr)
        return 1

    if not args.retract:
        preview: dict[str, Any] = {"dry_run": True, **plan.to_dict()}
        refusal = check_retraction_guardrails(plan, max_retraction_fraction=args.max_retraction_fraction)
        # Surfaced during the dry run too, so the operator learns the run would be refused
        # before they reach for --retract rather than after.
        preview["would_refuse"] = refusal
        print(json.dumps(preview, indent=2, sort_keys=True, default=str))
        return 0

    refusal = check_retraction_guardrails(plan, max_retraction_fraction=args.max_retraction_fraction)
    if refusal is not None:
        LOGGER.error("retraction_refused %s", refusal)
        refused = RetractionSummary(
            dry_run=True,
            canonical_documents=plan.canonical_documents,
            requested=len(plan.targets),
            matched=len(plan.found_targets),
            not_found=len(plan.missing_document_ids),
            reason_code=plan.reason_code,
            reason=plan.reason,
            retracted_by=plan.retracted_by,
            superseded_by_document_id=plan.superseded_by_document_id,
            not_found_document_ids=list(plan.missing_document_ids),
            failed=True,
            failure_reason=refusal,
        )
        print(json.dumps(refused.to_dict(), indent=2, sort_keys=True, default=str), file=sys.stderr)
        return 1

    try:
        summary = retractor.retract(plan)
    except Exception as exc:
        LOGGER.exception("canonical retraction failed")
        print(json.dumps({"status": "failed", "error": str(exc)}, indent=2), file=sys.stderr)
        return 1

    if summary.retracted:
        LOGGER.info(
            "retraction_complete retracted=%d — the search index still holds these documents; "
            "run document_intelligence_projection_reconcile --delete-orphans to de-index them",
            summary.retracted,
        )
    print(json.dumps(summary.to_dict(), indent=2, sort_keys=True, default=str))
    return 1 if summary.failed else 0


if __name__ == "__main__":
    raise SystemExit(main(sys.argv[1:]))
