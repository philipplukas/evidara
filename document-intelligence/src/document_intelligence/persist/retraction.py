"""Retract canonical rows from the Delta published surfaces (ADR-0057, issue #806).

``persist.sinks`` only ever appends. That is correct for the pipeline — canonical truth
is accumulated, not edited — but it left the platform with **no way at all** to remove a
canonical row that should never have been published: a duplicate minted by a pre-#652
identity key, an erroneous publication, a takedown. The only available procedure was a
hand-run object-store deletion: no guardrails, no record, no undo.

Two things make that gap load-bearing rather than cosmetic:

- ``projection_reconcile`` de-indexes *index minus canonical*. A duplicate that **has** a
  canonical row is not an orphan, so reconcile will not touch it. Canonical has to lose
  the row first; the index follows.
- Re-acquiring does not converge either. The post-#652 locator-keyed hash mints a *third*
  ``document_id``, so a re-run adds a row rather than replacing the stale ones.

What this module does, and deliberately does not do:

- **Retraction, not silent deletion.** Every removal appends a row to the
  ``canonical_retractions`` ledger *before* any row is deleted, recording what is going,
  why, on whose authority, and the Delta table version to restore to. A crash between the
  two leaves a ledger row for a document that still exists — visible and re-runnable.
  The reverse order would leave a deleted row with no record, which is the failure being
  designed out.
- **No ``lifecycle_status`` tombstone.** ``lifecycle_status`` is a *legal* claim about the
  norm (``active`` / ``superseded`` / ``repealed`` / ``withdrawn``). Marking a duplicate
  row of the Bundesverfassung ``withdrawn`` would assert, to every consumer, that Swiss
  constitutional law is no longer in force. Data-quality state and legal state are not
  the same axis and must not share a field. See ADR-0057 §Decision.
- **No ``VACUUM``.** A Delta ``DELETE`` is a new commit: the prior version stays readable
  via ``load_as_version`` and reversible via ``restore``, and the Parquet files survive
  until vacuumed. Not vacuuming is what keeps a retraction undoable, so this module
  never offers it.
- **``processing_manifests`` is never touched.** The manifest records that a run produced
  an output. That happened; deleting it would falsify run history. The manifest plus the
  retraction ledger together tell the whole story — a manifest whose
  ``published_document_ref`` no longer resolves is exactly the intended signal.
"""

from __future__ import annotations

import importlib
import logging
import re
from collections.abc import Iterable, Mapping, Sequence
from dataclasses import asdict, dataclass, field
from datetime import UTC, datetime
from typing import Any

from document_intelligence.canonical.ids import random_prefixed_id
from document_intelligence.errors import ProcessingError
from document_intelligence.persist.sinks import delta_string_equals
from document_intelligence.persist.surfaces import (
    CANONICAL_RETRACTIONS,
    PUBLISHED_DOCUMENTS,
    PUBLISHED_SECTIONS,
)

logger = logging.getLogger(__name__)

# The retraction job builds SQL delete predicates from operator input. Every id is matched
# against its canonical pattern before it reaches a predicate, so a value that could change
# the meaning of the predicate is rejected as invalid rather than escaped.
DOCUMENT_ID_PATTERN = re.compile(r"^doc_[0-9a-hjkmnp-tv-z]{26}$")

# Closed vocabulary. An operator who cannot classify the removal under one of these does
# not yet understand it well enough to remove canonical truth.
RETRACTION_REASON_CODES: dict[str, str] = {
    "duplicate_identity": (
        "The row duplicates a surviving document under an older identity key. "
        "Requires --superseded-by naming the surviving document, which must exist in canonical."
    ),
    "erroneous_publication": "The row should never have been published (stub, test artifact, mis-parse).",
    "takedown": "Removal compelled by a legal or contractual obligation.",
}

_SUPERSEDED_BY_REQUIRED_FOR = frozenset({"duplicate_identity"})

DEFAULT_MAX_RETRACTION_FRACTION = 0.10


@dataclass(frozen=True)
class DocumentRetractionTarget:
    """One document identity resolved against canonical, before anything is removed."""

    document_id: str
    document_rows: int = 0
    section_rows: int = 0
    revisions: tuple[int, ...] = ()
    titles: tuple[str, ...] = ()

    @property
    def found(self) -> bool:
        return self.document_rows > 0

    def to_dict(self) -> dict[str, Any]:
        return {
            "document_id": self.document_id,
            "document_rows": self.document_rows,
            "section_rows": self.section_rows,
            "revisions": list(self.revisions),
            "titles": list(self.titles),
            "found": self.found,
        }


@dataclass(frozen=True)
class RetractionPlan:
    """What a retraction *would* remove, evaluated against canonical before any mutation."""

    targets: tuple[DocumentRetractionTarget, ...]
    canonical_documents: int
    reason_code: str
    reason: str
    retracted_by: str
    superseded_by_document_id: str | None = None
    superseded_by_present: bool = False

    @property
    def found_targets(self) -> tuple[DocumentRetractionTarget, ...]:
        return tuple(target for target in self.targets if target.found)

    @property
    def missing_document_ids(self) -> tuple[str, ...]:
        return tuple(target.document_id for target in self.targets if not target.found)

    def to_dict(self) -> dict[str, Any]:
        return {
            "canonical_documents": self.canonical_documents,
            "reason_code": self.reason_code,
            "reason": self.reason,
            "retracted_by": self.retracted_by,
            "superseded_by_document_id": self.superseded_by_document_id,
            "superseded_by_present": self.superseded_by_present,
            "targets": [target.to_dict() for target in self.targets],
            "missing_document_ids": list(self.missing_document_ids),
        }


@dataclass
class SurfaceRetractionOutcome:
    """What one Delta surface actually did when the delete was committed."""

    surface_name: str
    uri: str
    rows_matched: int
    version_before: int | None = None
    rows_removed: int | None = None
    version_after: int | None = None

    def to_dict(self) -> dict[str, Any]:
        return asdict(self)


@dataclass
class RetractionSummary:
    """Outcome of one retraction run (printed as JSON so operators can diff runs)."""

    dry_run: bool = True
    canonical_documents: int = 0
    requested: int = 0
    matched: int = 0
    not_found: int = 0
    retracted: int = 0
    reason_code: str = ""
    reason: str = ""
    retracted_by: str = ""
    superseded_by_document_id: str | None = None
    failed: bool = False
    failure_reason: str | None = None
    retraction_ids: list[str] = field(default_factory=list)
    retracted_document_ids: list[str] = field(default_factory=list)
    not_found_document_ids: list[str] = field(default_factory=list)
    surfaces: list[dict[str, Any]] = field(default_factory=list)

    def to_dict(self) -> dict[str, Any]:
        return asdict(self)


def check_retraction_guardrails(
    plan: RetractionPlan,
    *,
    max_retraction_fraction: float = DEFAULT_MAX_RETRACTION_FRACTION,
) -> str | None:
    """Return a refusal reason when the plan looks unsafe, else ``None``.

    Mirrors ``projection_reconcile.check_delete_guardrails`` in shape, but the bounds are
    tighter by an order of magnitude on purpose: reconcile rebuilds a *derived* view from
    truth, whereas this removes truth itself. A wrong de-index is repaired by a backfill;
    a wrong retraction is repaired only by a Delta ``restore``, which someone has to
    notice is needed.

    Note what is *not* a refusal: a target that canonical does not have. That is the
    second run of a completed retraction, and it must succeed as a no-op.
    """
    if plan.reason_code not in RETRACTION_REASON_CODES:
        return f"unknown --reason-code {plan.reason_code!r}; expected one of {sorted(RETRACTION_REASON_CODES)}"
    if not plan.reason.strip():
        return "--reason is required: an unexplained canonical deletion is the thing this job exists to prevent"
    if not plan.retracted_by.strip():
        return "--retracted-by is required: canonical removals carry operator attribution (ADR-0038)"

    if plan.canonical_documents == 0:
        return (
            "canonical Delta enumerated 0 documents — refusing to retract against what "
            "reads as an empty corpus; check DI_SURFACES_ROOT_URI / DI_S3_* and re-run"
        )

    if plan.reason_code in _SUPERSEDED_BY_REQUIRED_FOR:
        if not plan.superseded_by_document_id:
            return (
                f"--reason-code {plan.reason_code} requires --superseded-by: removing a duplicate "
                "is only safe if the identity it duplicates survives"
            )
        if not plan.superseded_by_present:
            return (
                f"--superseded-by {plan.superseded_by_document_id} has no canonical published_documents "
                "row — retracting would delete the corpus's only copy of this document"
            )
        if any(target.document_id == plan.superseded_by_document_id for target in plan.targets):
            return (
                f"--superseded-by {plan.superseded_by_document_id} is itself in the retraction set; "
                "that removes both the duplicate and the survivor"
            )

    matched = len(plan.found_targets)
    if matched == 0:
        return None
    fraction = matched / plan.canonical_documents
    if fraction > max_retraction_fraction:
        return (
            f"{matched}/{plan.canonical_documents} canonical documents "
            f"({fraction:.0%}) would be retracted, above --max-retraction-fraction "
            f"{max_retraction_fraction:.0%}. Review the dry-run plan; raise the bound "
            f"deliberately if this is expected."
        )
    return None


class DeltaCanonicalRetractor:
    """Resolve, record and remove canonical rows on the Delta published surfaces.

    ``delta`` and ``writer`` are injectable so the resolution and ordering logic is unit
    testable without an object store; the tests also drive it against real local Delta
    tables, because the ordering guarantee ("ledger before delete") is only worth
    anything if it holds against the real transaction log.
    """

    def __init__(
        self,
        published_documents_uri: str,
        published_sections_uri: str,
        canonical_retractions_uri: str,
        *,
        storage_options: Mapping[str, str] | None = None,
        delta_module: Any | None = None,
    ) -> None:
        self._published_documents_uri = published_documents_uri
        self._published_sections_uri = published_sections_uri
        self._canonical_retractions_uri = canonical_retractions_uri
        self._storage_options = dict(storage_options) if storage_options else None
        self._delta_module = delta_module

    # -- resolution ---------------------------------------------------------------

    def plan(
        self,
        document_ids: Sequence[str],
        *,
        reason_code: str,
        reason: str,
        retracted_by: str,
        superseded_by_document_id: str | None = None,
    ) -> RetractionPlan:
        """Resolve every requested id against canonical without mutating anything."""
        for document_id in [*document_ids, *([superseded_by_document_id] if superseded_by_document_id else [])]:
            _require_document_id(document_id)

        targets = tuple(self._resolve_target(document_id) for document_id in dict.fromkeys(document_ids))
        superseded_by_present = (
            self._count_document_rows(superseded_by_document_id)[0] > 0 if superseded_by_document_id else False
        )
        return RetractionPlan(
            targets=targets,
            canonical_documents=self.canonical_document_count(),
            reason_code=reason_code,
            reason=reason,
            retracted_by=retracted_by,
            superseded_by_document_id=superseded_by_document_id,
            superseded_by_present=superseded_by_present,
        )

    def canonical_document_count(self) -> int:
        """Distinct ``document_id`` values on ``published_documents``."""
        table = self._scan(self._published_documents_uri, columns=["document_id"])
        if table is None:
            return 0
        return len({value for value in table.column("document_id").to_pylist() if isinstance(value, str)})

    def _resolve_target(self, document_id: str) -> DocumentRetractionTarget:
        document_rows, revisions, titles = self._count_document_rows(document_id)
        return DocumentRetractionTarget(
            document_id=document_id,
            document_rows=document_rows,
            section_rows=self._count_section_rows(document_id),
            revisions=revisions,
            titles=titles,
        )

    def _count_document_rows(self, document_id: str) -> tuple[int, tuple[int, ...], tuple[str, ...]]:
        table = self._scan(
            self._published_documents_uri,
            columns=["document_id", "document_revision", "title"],
            document_id=document_id,
        )
        if table is None:
            return 0, (), ()
        revisions = sorted({value for value in table.column("document_revision").to_pylist() if isinstance(value, int)})
        titles = sorted({value for value in table.column("title").to_pylist() if isinstance(value, str)})
        return table.num_rows, tuple(revisions), tuple(titles)

    def _count_section_rows(self, document_id: str) -> int:
        table = self._scan(
            self._published_sections_uri,
            columns=["document_id"],
            document_id=document_id,
        )
        return 0 if table is None else table.num_rows

    def _scan(self, uri: str, *, columns: Sequence[str], document_id: str | None = None) -> Any | None:
        """Read ``columns`` from a Delta surface, or ``None`` when the surface is absent."""
        delta = self._delta()
        try:
            dataset = delta.DeltaTable(uri, **self._table_kwargs()).to_pyarrow_dataset()
        except Exception as error:
            if _is_missing_table(error):
                return None
            raise ProcessingError(
                "retraction_surface_unreadable",
                f"failed to read canonical surface {uri}",
            ) from error
        available = set(dataset.schema.names)
        selected = [name for name in columns if name in available]
        if "document_id" not in selected:
            return None
        table = dataset.to_table(
            columns=selected,
            filter=None if document_id is None else delta_string_equals("document_id", document_id),
        )
        # Absent optional columns (a legacy surface without `title`) must still yield a
        # column, or every caller has to branch on the schema.
        pa = importlib.import_module("pyarrow")
        for name in columns:
            if name not in available:
                table = table.append_column(name, pa.nulls(table.num_rows))
        return table

    # -- mutation -----------------------------------------------------------------

    def retract(
        self,
        plan: RetractionPlan,
        *,
        now: datetime | None = None,
    ) -> RetractionSummary:
        """Record then remove every found target. Callers must run the guardrails first.

        Per document, in this order and no other:

        1. append the ledger row (what, why, who, and the Delta version to restore to),
        2. delete from ``published_sections``,
        3. delete from ``published_documents``.

        Sections go before documents so an interrupted run never leaves a document row
        whose sections are already gone — a half-retracted document that still answers a
        detail read would serve a body with no provisions.
        """
        summary = RetractionSummary(
            dry_run=False,
            canonical_documents=plan.canonical_documents,
            requested=len(plan.targets),
            matched=len(plan.found_targets),
            not_found=len(plan.missing_document_ids),
            reason_code=plan.reason_code,
            reason=plan.reason,
            retracted_by=plan.retracted_by,
            superseded_by_document_id=plan.superseded_by_document_id,
            not_found_document_ids=list(plan.missing_document_ids),
        )
        for document_id in plan.missing_document_ids:
            logger.info(
                "retraction_not_found document_id=%s (already retracted, or never canonical)",
                document_id,
            )

        for target in plan.found_targets:
            outcomes = [
                SurfaceRetractionOutcome(
                    surface_name=PUBLISHED_DOCUMENTS.surface_name,
                    uri=self._published_documents_uri,
                    rows_matched=target.document_rows,
                    version_before=self._table_version(self._published_documents_uri),
                ),
                SurfaceRetractionOutcome(
                    surface_name=PUBLISHED_SECTIONS.surface_name,
                    uri=self._published_sections_uri,
                    rows_matched=target.section_rows,
                    version_before=self._table_version(self._published_sections_uri),
                ),
            ]

            retraction_id = random_prefixed_id("ret")
            try:
                self._append_ledger_row(
                    retraction_id=retraction_id,
                    target=target,
                    plan=plan,
                    outcomes=outcomes,
                    now=now or datetime.now(UTC),
                )
            except Exception as error:
                # Nothing has been deleted yet, and nothing will be: an unrecorded
                # retraction is the one outcome this design refuses to produce.
                summary.failed = True
                summary.failure_reason = f"{target.document_id}: ledger append failed: {error}"
                logger.error(
                    "retraction_ledger_failed document_id=%s error=%s",
                    target.document_id,
                    error,
                )
                return summary

            try:
                for outcome in reversed(outcomes):  # sections, then documents
                    self._delete_rows(outcome, target.document_id)
            except Exception as error:
                summary.failed = True
                summary.failure_reason = f"{target.document_id}: delete failed: {error}"
                summary.retraction_ids.append(retraction_id)
                summary.surfaces.extend(outcome.to_dict() for outcome in outcomes)
                logger.error("retraction_delete_failed document_id=%s error=%s", target.document_id, error)
                return summary

            summary.retracted += 1
            summary.retraction_ids.append(retraction_id)
            summary.retracted_document_ids.append(target.document_id)
            summary.surfaces.extend(outcome.to_dict() for outcome in outcomes)
            logger.info(
                "retraction_committed retraction_id=%s document_id=%s revisions=%s "
                "document_rows=%s section_rows=%s reason_code=%s retracted_by=%s restore_versions=%s",
                retraction_id,
                target.document_id,
                list(target.revisions),
                outcomes[0].rows_removed,
                outcomes[1].rows_removed,
                plan.reason_code,
                plan.retracted_by,
                {outcome.surface_name: outcome.version_before for outcome in outcomes},
            )

        return summary

    def _delete_rows(self, outcome: SurfaceRetractionOutcome, document_id: str) -> None:
        if outcome.rows_matched == 0:
            outcome.rows_removed = 0
            outcome.version_after = outcome.version_before
            return
        delta = self._delta()
        table = delta.DeltaTable(outcome.uri, **self._table_kwargs())
        result = table.delete(predicate=f"document_id = '{_require_document_id(document_id)}'")
        removed = result.get("num_deleted_rows") if isinstance(result, Mapping) else None
        outcome.rows_removed = int(removed) if isinstance(removed, int) else None
        outcome.version_after = self._table_version(outcome.uri)
        if outcome.rows_removed is not None and outcome.rows_removed != outcome.rows_matched:
            # Not fatal: a concurrent append between plan and delete is legitimate. It is
            # logged because it means the ledger's `rows_matched` under-reports.
            logger.warning(
                "retraction_row_count_drift surface=%s document_id=%s matched=%s removed=%s",
                outcome.surface_name,
                document_id,
                outcome.rows_matched,
                outcome.rows_removed,
            )

    def _append_ledger_row(
        self,
        *,
        retraction_id: str,
        target: DocumentRetractionTarget,
        plan: RetractionPlan,
        outcomes: Iterable[SurfaceRetractionOutcome],
        now: datetime,
    ) -> None:
        pa = importlib.import_module("pyarrow")
        row = {
            "retraction_id": retraction_id,
            "document_id": target.document_id,
            "retracted_revisions": [int(revision) for revision in target.revisions],
            "reason_code": plan.reason_code,
            "reason": plan.reason,
            "superseded_by_document_id": plan.superseded_by_document_id,
            "retracted_by": plan.retracted_by,
            "retracted_at": now,
            # `rows_matched` and `version_before` are what the ledger can honestly promise:
            # both are known *before* the delete, and `version_before` is the restore point.
            # Post-delete counts live in the run summary, not here.
            "surfaces": [
                {
                    "surface_name": outcome.surface_name,
                    "uri": outcome.uri,
                    "rows_matched": outcome.rows_matched,
                    "version_before": outcome.version_before,
                }
                for outcome in outcomes
            ],
        }
        delta = self._delta()
        kwargs: dict[str, Any] = {"mode": "append", "schema_mode": "merge"}
        if self._storage_options:
            kwargs["storage_options"] = self._storage_options
        delta.write_deltalake(self._canonical_retractions_uri, pa.Table.from_pylist([row]), **kwargs)
        logger.info(
            "retraction_recorded retraction_id=%s document_id=%s ledger=%s",
            retraction_id,
            target.document_id,
            CANONICAL_RETRACTIONS.surface_name,
        )

    # -- plumbing -----------------------------------------------------------------

    def _table_version(self, uri: str) -> int | None:
        delta = self._delta()
        try:
            return int(delta.DeltaTable(uri, **self._table_kwargs()).version())
        except Exception as error:
            if _is_missing_table(error):
                return None
            raise

    def _table_kwargs(self) -> dict[str, Any]:
        return {"storage_options": self._storage_options} if self._storage_options else {}

    def _delta(self) -> Any:
        if self._delta_module is None:
            try:
                self._delta_module = importlib.import_module("deltalake")
            except ModuleNotFoundError as error:  # pragma: no cover - depends on env
                raise ProcessingError(
                    "missing_delta_dependency",
                    "deltalake is required to retract canonical rows",
                ) from error
        return self._delta_module


def _require_document_id(document_id: str) -> str:
    """Reject anything that is not a canonical document id before it reaches a predicate."""
    if not isinstance(document_id, str) or not DOCUMENT_ID_PATTERN.fullmatch(document_id):
        raise ProcessingError(
            "retraction_invalid_document_id",
            f"{document_id!r} is not a canonical document_id (doc_<26 crockford chars>)",
        )
    return document_id


def _is_missing_table(error: BaseException) -> bool:
    """Whether ``error`` means "this Delta surface does not exist yet".

    Matched on the exception *name*, exactly as ``persist.sinks`` does: the concrete type
    lives in the native ``deltalake._internal`` module and has moved between releases.
    """
    return type(error).__name__ == "TableNotFoundError"
