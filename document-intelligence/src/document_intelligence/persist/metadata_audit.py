"""Audit a canonical table for metadata the write path silently dropped (#871, step 2).

Widening the schema (#904, #940) stops the loss going forward. It does **not** backfill:
a table whose first batch lacked a key has already discarded that key from every batch
written after it, and nothing in the table records that this happened. This module answers
the only question that matters before a repair is planned:

    for this table, which keys are absent — and is each one *absent because nothing ever
    produced it*, or *absent because the write dropped it*?

Those two look identical in the data, which is exactly the failure ADR-0052 and the #958
milestone exist to end. They are separated here by three distinct kinds of evidence, and
where none of the three applies the answer is ``INDETERMINATE`` — never a guess.

**Evidence 1 — the declared struct.** A key the column's struct does not declare cannot be
in any row: the cast in ``_write_rows`` removed it before ``write_deltalake`` saw the batch.
So *undeclared* proves the table cannot hold the key, but on its own it does not prove any
document ever carried one.

**Evidence 2 — an unconditional emitter.** Some keys are written by the pipeline for every
document with a value that cannot be null: ``metadata.source_origin_kind`` and
``metadata.trust_tier`` come from required manifest fields
(``contracts/envelope.py:296-297``, ``:340-358``), and ``provenance``'s six required fields
plus the four ``_build_canonical_provenance`` sets (``pipeline.py:197-203``) are on every
canonical row by construction. For those, absent **is** dropped — no witness needed.

**Evidence 3 — a witness inside the same row.** Most keys are conditional, so their absence
is only a loss if the pipeline actually resolved a value. A witness is a *different* field of
the same row whose presence the code makes sufficient for the key having been emitted — e.g.
``metadata.field_provenance.in_force_from`` is set from the same ``in_force_window`` mapping
that sets ``metadata.in_force_from`` (``pipeline.py:736-739``, ``:834-836``). A fired witness
beside an absent key is proof of a drop.

What this module deliberately refuses to conclude:

* **Absence of a witness is not evidence of absence.** The witnesses cover the routes named
  in the registry, not every route (``_resolve_official_citation`` has an explicit-value route
  that leaves no trace in the row at all). An undeclared key with no fired witness is
  ``INDETERMINATE``, never ``NEVER_EMITTED``.
* **A witness that is itself missing from the schema proves nothing** — it may have been
  dropped by the same mechanism. It is reported as unavailable, and the finding stays
  ``INDETERMINATE``.
* **An empty table is not evidence.** Every finding over zero rows is ``INDETERMINATE``.
* **A surface it has no registry for.** The registry is a claim about *that surface's
  producer*; applied to another surface it is wrong in both directions at once — it reports
  keys that producer never writes as lost, and stays silent about every key it does write.
  Measured against production on 2026-09-19, auditing ``published_sections`` with the
  document registry called ``source_origin_kind`` and ``trust_tier`` lost on all 57,128 rows,
  citing ``pipeline.py:721`` — a line in ``_build_document``, which never touches a section
  row — while registering none of the eleven keys sections actually carry. An unknown surface
  is now refused (``UnknownSurfaceError``).

``NEVER_EMITTED`` is claimed in exactly one situation: the key **is** declared — so the cast
preserved whatever the batch carried — and is null on every row. That, and only that, is
upstream truth.

Everything here is read-only. ``plan_repair`` produces a plan; it executes nothing.
"""

from __future__ import annotations

import argparse
import json
import sys
from collections.abc import Mapping, Sequence
from dataclasses import dataclass, field
from enum import StrEnum

CANONICAL_STRUCT_COLUMNS: tuple[str, ...] = ("metadata", "provenance")


class Status(StrEnum):
    """What the audit can say about one key on one table."""

    PRESENT = "present"
    DROPPED = "dropped"
    NEVER_EMITTED = "never_emitted"
    INDETERMINATE = "indeterminate"


@dataclass(frozen=True)
class Witness:
    """A field of the same row whose presence implies the audited key was emitted."""

    path: tuple[str, ...]
    why: str


@dataclass(frozen=True)
class EmittedKey:
    """A key the pipeline can write into a canonical struct column."""

    column: str
    key: str
    emitter: str
    unconditional: bool = False
    witnesses: tuple[Witness, ...] = ()


_PROVENANCE_REQUIRED = (
    "tenant_id",
    "corpus_id",
    "scope_type",
    "source_id",
    "source_version_id",
    "run_id",
)
_PROVENANCE_CANONICAL = (
    "artifact_id",
    "document_id",
    "document_revision",
    "processing_manifest_id",
)

#: Every key the pipeline can write into an audited struct column **of a document row**.
#:
#: Scoped to ``published_documents`` on purpose: these are ``_build_document``'s keys
#: (``pipeline.py:720-838``). A *section* row's ``metadata`` is a different dictionary built
#: by ``_build_sections`` (``pipeline.py:962-999``) and it never carries any of them — so
#: auditing ``published_sections`` against this registry reports two unconditional keys as
#: lost on every row of that surface, which is a manufactured repair plan rather than a
#: finding. See ``SURFACE_REGISTRIES``.
#:
#: Hand-written on purpose — ``unconditional`` and ``witnesses`` are claims about the code
#: that no AST scan can derive — and drift-guarded: ``test_metadata_audit.py`` re-derives the
#: statically visible ``metadata["..."] = `` assignments from ``pipeline.py`` and fails when
#: one of them is not registered here. Add the key *and* say whether anything witnesses it.
EMITTED_KEYS: tuple[EmittedKey, ...] = (
    # --- metadata: unconditional -------------------------------------------------------
    EmittedKey(
        column="metadata",
        key="source_origin_kind",
        emitter="pipeline.py:721",
        unconditional=True,
    ),
    EmittedKey(
        column="metadata",
        key="trust_tier",
        emitter="pipeline.py:722",
        unconditional=True,
    ),
    # --- metadata: conditional ---------------------------------------------------------
    EmittedKey(column="metadata", key="normalizer", emitter="pipeline.py:720"),
    EmittedKey(column="metadata", key="source_defaults", emitter="pipeline.py:723"),
    EmittedKey(column="metadata", key="extracted_metadata", emitter="pipeline.py:728"),
    EmittedKey(column="metadata", key="extraction_hints", emitter="pipeline.py:731"),
    EmittedKey(
        column="metadata",
        key="in_force_from",
        emitter="pipeline.py:740 (via _resolve_in_force_window, pipeline.py:690-702)",
        witnesses=(
            Witness(
                path=("field_provenance", "in_force_from"),
                why=(
                    "the same `in_force_window` entry that sets metadata.in_force_from "
                    "(pipeline.py:738-740) is recorded on the provenance audit "
                    "(pipeline.py:834-836)"
                ),
            ),
            Witness(
                path=("extraction_hints", "in_force_from_hint"),
                why="a hint present on the row is route 1 of _resolve_in_force_window (pipeline.py:695-698)",
            ),
            Witness(
                path=("extracted_metadata", "in_force_from"),
                why="route 2 of _resolve_in_force_window (pipeline.py:699-702)",
            ),
        ),
    ),
    EmittedKey(
        column="metadata",
        key="in_force_until",
        emitter="pipeline.py:740 (via _resolve_in_force_window, pipeline.py:690-702)",
        witnesses=(
            Witness(
                path=("field_provenance", "in_force_until"),
                why="as in_force_from — pipeline.py:834-836",
            ),
            Witness(
                path=("extraction_hints", "in_force_until_hint"),
                why="route 1 of _resolve_in_force_window (pipeline.py:695-698)",
            ),
            Witness(
                path=("extracted_metadata", "in_force_until"),
                why="route 2 of _resolve_in_force_window (pipeline.py:699-702)",
            ),
        ),
    ),
    EmittedKey(
        column="metadata",
        key="official_citation",
        emitter="pipeline.py:743 (via _resolve_official_citation, pipeline.py:863-900)",
        witnesses=(
            Witness(
                path=("extracted_metadata", "publication_organ"),
                why="route 2 of _resolve_official_citation returns it verbatim (pipeline.py:889-892)",
            ),
            Witness(
                path=("extracted_metadata", "kundmachungsorgan"),
                why="route 2 of _resolve_official_citation returns it verbatim (pipeline.py:889-892)",
            ),
            Witness(
                path=("field_provenance", "publication_organ"),
                why="the same extracted field, recorded on the provenance audit (pipeline.py:826-829)",
            ),
        ),
    ),
    EmittedKey(
        column="metadata",
        key="regeste",
        emitter="pipeline.py:750 (via _resolve_regeste, pipeline.py:902-944)",
        witnesses=(
            Witness(
                path=("extracted_metadata", "headnote"),
                why="route 2 of _resolve_regeste returns it (pipeline.py:920-923)",
            ),
        ),
    ),
    EmittedKey(
        column="metadata",
        key="original_language",
        emitter="pipeline.py:753",
        witnesses=(
            Witness(
                path=("translation_status",),
                why=(
                    "the two are set in one branch — translation_status exists on a row only "
                    "because original_language resolved (pipeline.py:751-754)"
                ),
            ),
        ),
    ),
    EmittedKey(
        column="metadata",
        key="translation_status",
        emitter="pipeline.py:754",
        witnesses=(
            Witness(
                path=("original_language",),
                why="the converse of the same branch (pipeline.py:751-754)",
            ),
        ),
    ),
    EmittedKey(column="metadata", key="source_flavor", emitter="pipeline.py:757"),
    EmittedKey(column="metadata", key="html_parse_used_fallback", emitter="pipeline.py:759"),
    EmittedKey(column="metadata", key="html_parse_recovery", emitter="pipeline.py:762"),
    EmittedKey(column="metadata", key="docling", emitter="pipeline.py:765"),
    EmittedKey(column="metadata", key="llm_extraction", emitter="pipeline.py:773,781"),
    EmittedKey(column="metadata", key="field_provenance", emitter="pipeline.py:838"),
    EmittedKey(column="metadata", key="nlp", emitter="pipeline.py:314"),
    EmittedKey(column="metadata", key="commentary_insights", emitter="pipeline.py:346"),
    # --- provenance --------------------------------------------------------------------
    *(
        EmittedKey(
            column="provenance",
            key=name,
            emitter="contracts/envelope.py:107-115 (required by Provenance.from_dict)",
            unconditional=True,
        )
        for name in _PROVENANCE_REQUIRED
    ),
    *(
        EmittedKey(
            column="provenance",
            key=name,
            emitter="pipeline.py:197-203 (_build_canonical_provenance sets it on every canonical row)",
            unconditional=True,
        )
        for name in _PROVENANCE_CANONICAL
    ),
    EmittedKey(
        column="provenance",
        key="source_snapshot_id",
        emitter="contracts/envelope.py:143-144 (omitted by to_dict when None)",
    ),
    EmittedKey(
        column="provenance",
        key="bundle_manifest_id",
        emitter="contracts/envelope.py:145-146 (omitted by to_dict when None)",
    ),
)


_PROVENANCE_KEYS: tuple[EmittedKey, ...] = tuple(spec for spec in EMITTED_KEYS if spec.column == "provenance")

#: Every key a **section** row can carry in ``metadata``.
#:
#: A section's metadata is ``{"heading_level", "block_id", **block.attrs}`` plus the ancestry
#: and citation keys (``sectionize/html.py:34-44``, ``pipeline.py:975-981``), and
#: ``block.attrs`` is open-ended and *normalizer-specific*: the PDF normalizer emits
#: ``page_no`` / ``bbox_top`` / ``marginal`` (``normalize/pdf.py:282-287``), the XML one
#: ``official_label`` / ``heading_text`` / ``typ`` (``normalize/xml.py:218-246``), the HTML one
#: ``anchor`` and the recovery flags (``normalize/html.py:174-186``, ``:217``, ``:252``).
#:
#: **Nothing here is unconditional.** ``sectionize/html.py:63-73`` has a whole-body fallback
#: that emits ``metadata={}``, so a section can legitimately carry no key at all. Declaring
#: any of these unconditional would reproduce the false loss this registry exists to stop.
SECTION_EMITTED_KEYS: tuple[EmittedKey, ...] = (
    EmittedKey(
        column="metadata",
        key="block_id",
        emitter="sectionize/html.py:35",
        witnesses=(
            Witness(
                path=("heading_level",),
                why=(
                    "both are set in one dict literal (sectionize/html.py:34-36) and `block.id` "
                    "is never None, so a heading_level on the row proves block_id was emitted"
                ),
            ),
        ),
    ),
    # `block.level` is None for an XML structural heading (normalize/xml.py:272), so a
    # present `block_id` does NOT imply a non-null heading_level. No witness.
    EmittedKey(column="metadata", key="heading_level", emitter="sectionize/html.py:34"),
    EmittedKey(column="metadata", key="citations", emitter="pipeline.py:981"),
    EmittedKey(
        column="metadata",
        key="ancestor_titles",
        emitter="sectionize/html.py:40",
        witnesses=(
            Witness(
                path=("parent_title",),
                why="set in the same `if ancestry:` branch (sectionize/html.py:40-41)",
            ),
        ),
    ),
    EmittedKey(
        column="metadata",
        key="parent_title",
        emitter="sectionize/html.py:41",
        witnesses=(
            Witness(
                path=("ancestor_titles",),
                why="the converse of the same branch (sectionize/html.py:40-41)",
            ),
        ),
    ),
    # Only set when the ancestor had an anchor, so `parent_title` is not sufficient.
    EmittedKey(column="metadata", key="parent_anchor", emitter="sectionize/html.py:44"),
    EmittedKey(column="metadata", key="tag", emitter="normalize/{html,pdf,xml}.py (block.attrs)"),
    EmittedKey(column="metadata", key="anchor", emitter="normalize/html.py:186, normalize/pdf.py:285"),
    EmittedKey(
        column="metadata",
        key="page_no",
        emitter="normalize/pdf.py:282",
        witnesses=(
            Witness(
                path=("bbox_top",),
                why="both are set in one dict literal on every PDF block (normalize/pdf.py:282)",
            ),
        ),
    ),
    EmittedKey(
        column="metadata",
        key="bbox_top",
        emitter="normalize/pdf.py:282",
        witnesses=(
            Witness(
                path=("page_no",),
                why="the converse of the same literal (normalize/pdf.py:282)",
            ),
        ),
    ),
    EmittedKey(column="metadata", key="marginal", emitter="normalize/pdf.py:287"),
    EmittedKey(column="metadata", key="official_label", emitter="normalize/xml.py:218-220, :273-275"),
    EmittedKey(column="metadata", key="heading_text", emitter="normalize/xml.py:218-220"),
    EmittedKey(column="metadata", key="typ", emitter="normalize/xml.py:246"),
    EmittedKey(column="metadata", key="fallback", emitter="normalize/xml.py:128, normalize/html.py:217,252"),
    EmittedKey(column="metadata", key="parse_error_recovery", emitter="normalize/html.py:217"),
    EmittedKey(column="metadata", key="format", emitter="normalize/html.py:297,316,330"),
    EmittedKey(column="metadata", key="normalizer", emitter="normalize/html.py:361"),
    *_PROVENANCE_KEYS,
)

#: A manifest row carries `provenance` and no `metadata` column at all
#: (`_PROCESSING_MANIFESTS_DELTA_KEYS`, `persist/sinks.py:56-74`).
MANIFEST_EMITTED_KEYS: tuple[EmittedKey, ...] = _PROVENANCE_KEYS

#: A retraction row (ADR-0057) carries neither audited struct column. An empty registry is
#: the honest answer — it yields no findings rather than 32 "cannot be established" ones.
RETRACTION_EMITTED_KEYS: tuple[EmittedKey, ...] = ()

#: Which registry each canonical surface is audited against.
#:
#: The registry is a claim about the **producer of that surface's rows**. Applying one
#: surface's registry to another is not a conservative default, it is a false verdict in
#: both directions at once: it manufactures losses for keys that surface never carried, and
#: it is silent about every key that surface actually does carry. A surface that is not here
#: is refused (``UnknownSurfaceError``) rather than audited against a guess.
SURFACE_REGISTRIES: dict[str, tuple[EmittedKey, ...]] = {
    "published_documents": EMITTED_KEYS,
    "published_sections": SECTION_EMITTED_KEYS,
    "processing_manifests": MANIFEST_EMITTED_KEYS,
    "canonical_retractions": RETRACTION_EMITTED_KEYS,
}


class UnknownSurfaceError(ValueError):
    """Raised rather than auditing a surface against a registry that may not describe it."""


def surface_name_from_uri(uri: str) -> str:
    """The surface name in a table URI — its last non-empty path segment."""

    trimmed = uri.rstrip("/")
    _, _, tail = trimmed.rpartition("/")
    return tail or trimmed


def registry_for_surface(surface: str) -> tuple[EmittedKey, ...]:
    """The registry for ``surface``, or a refusal naming the ones that exist."""

    try:
        return SURFACE_REGISTRIES[surface]
    except KeyError:
        known = ", ".join(sorted(SURFACE_REGISTRIES))
        raise UnknownSurfaceError(
            f"no emitted-key registry for surface {surface!r}: auditing it against another "
            f"surface's registry would report keys its producer never writes as lost, and "
            f"say nothing about the keys it does write. Known surfaces: {known}. "
            f"Pass --surface to name one explicitly."
        ) from None


@dataclass(frozen=True)
class KeyFinding:
    column: str
    key: str
    status: Status
    reason: str
    declared: bool
    rows_total: int
    rows_with_value: int = 0
    rows_with_witness: int = 0
    rows_witness_without_value: int = 0
    witnesses_available: tuple[str, ...] = ()
    witnesses_unavailable: tuple[str, ...] = ()

    def to_dict(self) -> dict[str, object]:
        return {
            "column": self.column,
            "key": self.key,
            "status": self.status.value,
            "reason": self.reason,
            "declared": self.declared,
            "rows_total": self.rows_total,
            "rows_with_value": self.rows_with_value,
            "rows_with_witness": self.rows_with_witness,
            "rows_witness_without_value": self.rows_witness_without_value,
            "witnesses_available": list(self.witnesses_available),
            "witnesses_unavailable": list(self.witnesses_unavailable),
        }


@dataclass(frozen=True)
class AuditReport:
    table_uri: str
    rows_total: int
    findings: tuple[KeyFinding, ...]
    undeclared_columns: tuple[str, ...] = ()
    unregistered_declared_fields: tuple[str, ...] = ()
    #: Which surface's registry produced these findings. Reported because a verdict is only
    #: meaningful against the producer it was derived from.
    surface: str = "<unspecified>"

    def with_status(self, status: Status) -> tuple[KeyFinding, ...]:
        return tuple(finding for finding in self.findings if finding.status is status)

    @property
    def dropped(self) -> tuple[KeyFinding, ...]:
        return self.with_status(Status.DROPPED)

    @property
    def indeterminate(self) -> tuple[KeyFinding, ...]:
        return self.with_status(Status.INDETERMINATE)

    def to_dict(self) -> dict[str, object]:
        return {
            "table_uri": self.table_uri,
            "surface": self.surface,
            "rows_total": self.rows_total,
            "undeclared_columns": list(self.undeclared_columns),
            "unregistered_declared_fields": list(self.unregistered_declared_fields),
            "findings": [finding.to_dict() for finding in self.findings],
        }


def _resolve(container: object, path: Sequence[str]) -> object:
    value: object = container
    for segment in path:
        if not isinstance(value, Mapping):
            return None
        value = value.get(segment)
    return value


def _fires(container: object, path: Sequence[str]) -> bool:
    """Whether a witness path holds a value the pipeline would have acted on.

    A blank string does not fire: every route a witness stands for guards on
    ``isinstance(value, str) and value.strip()`` (``pipeline.py:695-702``, ``:886-892``,
    ``:920-923``), so an empty string is a value the pipeline itself ignores. Firing on it
    would report a drop where none happened.
    """

    value = _resolve(container, path)
    if value is None:
        return False
    if isinstance(value, str):
        return bool(value.strip())
    return True


def audit_rows(
    *,
    declared_fields: Mapping[str, frozenset[str] | None],
    rows: Sequence[Mapping[str, object]],
    table_uri: str = "<rows>",
    keys: Sequence[EmittedKey] = EMITTED_KEYS,
    surface: str = "<unspecified>",
) -> AuditReport:
    """Classify every registered key against one table's declared schema and its rows.

    ``declared_fields`` maps a struct column to the field names its Arrow struct declares —
    or to ``None`` when the column is absent from the table, or is not a struct (a
    ``map<string,string>`` column cannot drop keys and is not audited here).

    ``keys`` must be the registry for the surface these rows came from. The default is the
    ``published_documents`` one because that is what this module was written for; every
    caller that knows its surface should resolve with ``registry_for_surface`` instead, and
    ``audit_delta_table`` does.
    """

    rows_total = len(rows)
    findings: list[KeyFinding] = []
    undeclared_columns = tuple(sorted(column for column, fields in declared_fields.items() if fields is None))

    for spec in keys:
        declared_here = declared_fields.get(spec.column)
        if declared_here is None:
            findings.append(
                KeyFinding(
                    column=spec.column,
                    key=spec.key,
                    status=Status.INDETERMINATE,
                    reason=(
                        f"column `{spec.column}` is absent from the table, or is not a struct — "
                        "nothing about this key can be established from it"
                    ),
                    declared=False,
                    rows_total=rows_total,
                )
            )
            continue

        declared = spec.key in declared_here
        available = tuple(w for w in spec.witnesses if w.path[0] in declared_here)
        unavailable = tuple(w for w in spec.witnesses if w.path[0] not in declared_here)
        available_paths = tuple(".".join(w.path) for w in available)
        unavailable_paths = tuple(".".join(w.path) for w in unavailable)

        rows_with_value = 0
        rows_with_witness = 0
        rows_witness_without_value = 0
        for row in rows:
            column_value = row.get(spec.column)
            has_value = _fires(column_value, (spec.key,))
            fired = any(_fires(column_value, w.path) for w in available)
            rows_with_value += int(has_value)
            rows_with_witness += int(fired)
            rows_witness_without_value += int(fired and not has_value)

        common = dict(
            column=spec.column,
            key=spec.key,
            declared=declared,
            rows_total=rows_total,
            rows_with_value=rows_with_value,
            rows_with_witness=rows_with_witness,
            rows_witness_without_value=rows_witness_without_value,
            witnesses_available=available_paths,
            witnesses_unavailable=unavailable_paths,
        )

        if rows_total == 0:
            # An empty table is not evidence of anything, in either direction.
            findings.append(
                KeyFinding(
                    status=Status.INDETERMINATE,
                    reason="the table holds no rows; absence here is not evidence",
                    **common,
                )
            )
            continue

        if rows_witness_without_value:
            findings.append(
                KeyFinding(
                    status=Status.DROPPED,
                    reason=(
                        f"{rows_witness_without_value} of {rows_total} rows carry a witness "
                        f"({', '.join(available_paths)}) with no value for this key — the pipeline "
                        f"resolved it and the write did not keep it ({spec.emitter})"
                    ),
                    **common,
                )
            )
            continue

        if not declared:
            if spec.unconditional:
                findings.append(
                    KeyFinding(
                        status=Status.DROPPED,
                        reason=(
                            "the struct does not declare this key, and the pipeline writes it with a "
                            f"non-null value on every canonical row ({spec.emitter}) — so every one of "
                            f"the {rows_total} rows lost it"
                        ),
                        **common,
                    )
                )
            else:
                witness_note = (
                    f"no witness fired (available: {', '.join(available_paths)})"
                    if available_paths
                    else "no witness for this key is available"
                )
                if unavailable_paths:
                    witness_note += (
                        f"; witnesses undeclared on this table and therefore themselves suspect: "
                        f"{', '.join(unavailable_paths)}"
                    )
                findings.append(
                    KeyFinding(
                        status=Status.INDETERMINATE,
                        reason=(
                            "the struct does not declare this key, so the table cannot hold it — but "
                            f"nothing here shows a document ever carried one: {witness_note}"
                        ),
                        **common,
                    )
                )
            continue

        if rows_with_value:
            findings.append(
                KeyFinding(
                    status=Status.PRESENT,
                    reason=f"declared, and populated on {rows_with_value} of {rows_total} rows",
                    **common,
                )
            )
            continue

        if spec.unconditional:
            findings.append(
                KeyFinding(
                    status=Status.DROPPED,
                    reason=(
                        "declared but null on every row, while the pipeline writes it with a non-null "
                        f"value on every canonical row ({spec.emitter}) — the rows did not come from "
                        "this pipeline, or the value was lost after it"
                    ),
                    **common,
                )
            )
            continue

        findings.append(
            KeyFinding(
                status=Status.NEVER_EMITTED,
                reason=(
                    "declared — so the write path preserved whatever each batch carried — and null on "
                    f"all {rows_total} rows: nothing upstream produced a value"
                ),
                **common,
            )
        )

    registered = {(spec.column, spec.key) for spec in keys}
    unregistered = tuple(
        sorted(
            f"{column}.{name}"
            for column, fields in declared_fields.items()
            if fields is not None
            for name in fields
            if (column, name) not in registered
        )
    )

    return AuditReport(
        table_uri=table_uri,
        rows_total=rows_total,
        findings=tuple(findings),
        undeclared_columns=undeclared_columns,
        unregistered_declared_fields=unregistered,
        surface=surface,
    )


def declared_struct_fields(
    schema: object,
    columns: Sequence[str] = CANONICAL_STRUCT_COLUMNS,
) -> dict[str, frozenset[str] | None]:
    """Read the declared struct field names out of a PyArrow schema.

    A column that is absent, or that is not a struct (``map<string,string>`` cannot drop a
    key), maps to ``None`` — "no claim can be made", not "empty".
    """

    import pyarrow as pa

    declared: dict[str, frozenset[str] | None] = {}
    for column in columns:
        if column not in schema.names:  # type: ignore[attr-defined]
            declared[column] = None
            continue
        field_type = schema.field(column).type  # type: ignore[attr-defined]
        if not pa.types.is_struct(field_type):
            declared[column] = None
            continue
        declared[column] = frozenset(field_type.field(i).name for i in range(field_type.num_fields))
    return declared


def audit_delta_table(
    uri: str,
    *,
    storage_options: Mapping[str, str] | None = None,
    columns: Sequence[str] = CANONICAL_STRUCT_COLUMNS,
    surface: str | None = None,
) -> AuditReport:
    """Read-only audit of a Delta canonical table. Opens the log and reads; writes nothing.

    The registry is resolved from ``surface`` — or, when it is not given, from the URI's last
    path segment. An unrecognised surface raises ``UnknownSurfaceError`` rather than falling
    back to the document registry, because that fallback is what produced a 57,128-row repair
    plan for two keys no section row has ever carried.
    """

    import deltalake

    resolved_surface = surface or surface_name_from_uri(uri)
    keys = registry_for_surface(resolved_surface)

    table = deltalake.DeltaTable(uri, storage_options=dict(storage_options or {}))
    schema = table.to_pyarrow_dataset().schema
    declared = declared_struct_fields(schema, columns)
    read_columns = [name for name in ("document_id", *columns) if name in schema.names]
    rows = table.to_pyarrow_table(columns=read_columns).to_pylist()
    return audit_rows(
        declared_fields=declared,
        rows=rows,
        table_uri=uri,
        keys=keys,
        surface=resolved_surface,
    )


# --------------------------------------------------------------------------------------
# Repair planning — produces a plan, executes nothing.
# --------------------------------------------------------------------------------------


@dataclass(frozen=True)
class RepairPlan:
    table_uri: str
    dropped_keys: tuple[str, ...]
    indeterminate_keys: tuple[str, ...]
    reprocess: tuple[dict[str, str], ...] = ()
    reacquire: tuple[str, ...] = ()
    notes: tuple[str, ...] = field(default_factory=tuple)

    def to_dict(self) -> dict[str, object]:
        return {
            "table_uri": self.table_uri,
            "dropped_keys": list(self.dropped_keys),
            "indeterminate_keys": list(self.indeterminate_keys),
            "reprocess": [dict(item) for item in self.reprocess],
            "reacquire": list(self.reacquire),
            "notes": list(self.notes),
        }


def plan_repair(report: AuditReport, rows: Sequence[Mapping[str, object]]) -> RepairPlan:
    """Say what a repair run would do. It performs none of it.

    A dropped key is not recoverable from the table — the value is gone — so the only repair
    is to publish a new ``document_revision`` from the raw bundle the document came from.
    Which bundle that is, is read from the row's own ``provenance``... which is a struct
    column exposed to the very same defect. A row whose ``provenance.bundle_manifest_id`` was
    dropped cannot be reprocessed from anything the platform holds: it has to be re-acquired
    from the authority. That is reported, not silently skipped.
    """

    dropped = tuple(f"{f.column}.{f.key}" for f in report.dropped)
    indeterminate = tuple(f"{f.column}.{f.key}" for f in report.indeterminate)
    notes: list[str] = []

    if not dropped:
        notes.append("no key is provably dropped on this table; a repair run would change nothing")
        if indeterminate:
            notes.append(
                f"{len(indeterminate)} key(s) are INDETERMINATE — absent with no witness either way. "
                "Resolve them against the source bundles before concluding the table is clean."
            )
        return RepairPlan(
            table_uri=report.table_uri,
            dropped_keys=(),
            indeterminate_keys=indeterminate,
            notes=tuple(notes),
        )

    reprocess: list[dict[str, str]] = []
    reacquire: list[str] = []
    for row in rows:
        provenance = row.get("provenance")
        provenance = provenance if isinstance(provenance, Mapping) else {}
        document_id = str(row.get("document_id") or provenance.get("document_id") or "<unknown>")
        bundle_manifest_id = provenance.get("bundle_manifest_id")
        if isinstance(bundle_manifest_id, str) and bundle_manifest_id:
            reprocess.append(
                {
                    "document_id": document_id,
                    "bundle_manifest_id": bundle_manifest_id,
                    "source_version_id": str(provenance.get("source_version_id") or "<unknown>"),
                }
            )
        else:
            reacquire.append(document_id)

    notes.append(
        "PRECONDITION: the widening fix (#904, #940) must be in the running image before any "
        "reprocess. Appending to the same narrow table from an old image narrows the batch again."
    )
    notes.append(
        "Reprocess, do not rebuild: `document_intelligence_delta_projection_backfill` replays what "
        "Delta holds and reproduces the absence faithfully (events/document_processed.py:139-140)."
    )
    if reacquire:
        notes.append(
            f"{len(reacquire)} row(s) carry no `provenance.bundle_manifest_id` — either the source "
            "never supplied one or this column was dropped too. They are not repairable from the "
            "platform's own state and must be re-acquired from the authority."
        )
    if indeterminate:
        notes.append(f"{len(indeterminate)} key(s) are INDETERMINATE and are NOT counted as loss here.")
    return RepairPlan(
        table_uri=report.table_uri,
        dropped_keys=dropped,
        indeterminate_keys=indeterminate,
        reprocess=tuple(reprocess),
        reacquire=tuple(reacquire),
        notes=tuple(notes),
    )


def render_text(report: AuditReport) -> str:
    lines = [
        f"table:   {report.table_uri}",
        f"surface: {report.surface} ({len(report.findings)} registered key(s))",
        f"rows:    {report.rows_total}",
        "",
    ]
    if not report.findings:
        lines.append("this surface has no audited struct columns; nothing here can be claimed")
        lines.append("")
    for status in (Status.DROPPED, Status.INDETERMINATE, Status.NEVER_EMITTED, Status.PRESENT):
        findings = report.with_status(status)
        if not findings:
            continue
        lines.append(f"{status.value.upper()} ({len(findings)})")
        for finding in findings:
            lines.append(f"  {finding.column}.{finding.key}: {finding.reason}")
        lines.append("")
    if report.undeclared_columns:
        lines.append(f"columns not audited (absent or not a struct): {', '.join(report.undeclared_columns)}")
    if report.unregistered_declared_fields:
        lines.append(
            "declared but unknown to this pipeline (stale, or produced elsewhere): "
            + ", ".join(report.unregistered_declared_fields)
        )
    return "\n".join(lines)


def main(argv: Sequence[str] | None = None) -> int:
    parser = argparse.ArgumentParser(
        prog="python -m document_intelligence.persist.metadata_audit",
        description="Read-only audit of a canonical Delta table for metadata the write dropped (#871).",
    )
    parser.add_argument("--uri", required=True, help="Delta table URI (file path, s3://, gs://)")
    parser.add_argument("--json", action="store_true", help="emit JSON instead of text")
    parser.add_argument("--plan", action="store_true", help="also print the repair plan (executes nothing)")
    parser.add_argument(
        "--surface",
        default=None,
        choices=sorted(SURFACE_REGISTRIES),
        help="which surface's emitted-key registry to audit against (default: read from the URI)",
    )
    args = parser.parse_args(argv)

    from document_intelligence.persist.sinks import delta_storage_options

    try:
        report = audit_delta_table(
            args.uri,
            storage_options=delta_storage_options() or {},
            surface=args.surface,
        )
    except UnknownSurfaceError as error:
        print(f"refusing to audit: {error}", file=sys.stderr)
        return 2
    payload: dict[str, object] = {"audit": report.to_dict()}
    text = [render_text(report)]
    if args.plan:
        import deltalake

        rows = (
            deltalake.DeltaTable(args.uri, storage_options=delta_storage_options() or {}).to_pyarrow_table().to_pylist()
        )
        plan = plan_repair(report, rows)
        payload["repair_plan"] = plan.to_dict()
        text.append("")
        text.append("REPAIR PLAN (nothing has been executed)")
        text.append(f"  reprocess: {len(plan.reprocess)} document(s)")
        text.append(f"  re-acquire: {len(plan.reacquire)} document(s)")
        for note in plan.notes:
            text.append(f"  - {note}")

    print(json.dumps(payload, indent=2) if args.json else "\n".join(text))
    return 0


if __name__ == "__main__":  # pragma: no cover - CLI entry
    sys.exit(main())
