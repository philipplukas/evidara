# ADR-0057: Retraction is a record, not a deletion — and never a legal claim

## Status

Proposed

## Date

2026-09-10

## Context

### Canonical had no way to say "this row should never have existed"

`document_intelligence/persist/sinks.py` only ever appends. That is right for the pipeline
— canonical truth is accumulated, not edited — but until this ADR it left the platform
with **no way at all** to remove a canonical row that should not be there. `grep -rln -i
retract` across `legal-search/api/src`, `document-intelligence/src` and
`platform-control/src` returned nothing.

#806 is the case that made the gap load-bearing: the production index holds the
Bundesverfassung twice, because a pre-#652 identity key minted a second `document_id` for
the same norm. Two things mean the existing machinery cannot converge on that:

- **`projection_reconcile` de-indexes *index minus canonical*.** A duplicate that still
  *has* a canonical row is not an orphan, so reconcile will not touch it, and every
  backfill re-projects it.
- **Re-acquiring does not converge either.** The post-#652 locator-keyed hash mints a
  *third* `document_id`, so a re-run adds a row rather than replacing the stale ones.

The only available procedure was a hand-run object-store deletion: no guardrails, no
record, no undo.

### Why this is the #958 milestone's shape

#958 asks that the corpus "states what is true, or refuses". A known-wrong record and a
correct one being indistinguishable to every consumer is the same defect as *absent*
versus *broken* — with the extra hazard that the wrong record is the one that sounds
authoritative. Removing it silently swaps one indistinguishability for another: afterwards
nobody can tell a document that was retracted from one that was never acquired.

## Decision

**Removing a canonical row is a recorded, bounded, reversible operation, and it never
makes a claim about the law.** Four rules, in the order they bind.

### 1. The ledger is written before anything is deleted

Every removal appends a row to a new append-only Delta surface,
`canonical_retractions`, recording *what* is going, *why* (a closed reason vocabulary plus
a mandatory narrative), *on whose authority*, and the **pre-delete Delta table version to
restore to** — and only then issues the `DELETE`.

The ordering is the whole design. A crash between the two leaves a ledger row for a
document that still exists: visible, explicable, and re-runnable, because the operation is
idempotent. The reverse order leaves a deleted row with no record — which is the failure
being designed out, and is exactly what the hand-run deletion produced.

If the ledger append fails, **nothing is deleted and the run reports failure.** An
unrecorded retraction is the one outcome this design refuses to produce.

Within a document, sections are deleted before the document row. An interrupted run must
never leave a document row whose sections are already gone, because that row still answers
a detail read — with a body and no provisions. The reverse leaves an orphan section set,
which no read path serves.

### 2. No `lifecycle_status` tombstone. Data-quality state and legal state are different axes

`lifecycle_status` is a *legal* claim about the norm: `active` / `superseded` / `repealed`
/ `withdrawn`. It is what a point-in-time query reads, and what a user reads as "is this
good law".

Marking the duplicate Bundesverfassung row `withdrawn` because *our record* of it was
wrong would assert, to every consumer downstream, that **Swiss constitutional law is no
longer in force**. That is not a smaller error than the duplicate; it is a much larger
one, and it is the kind of error a demo answers confidently — the failure mode ADR-0033
names as worse than failing.

So: a retraction removes the row and records why in a ledger whose vocabulary is about
*records* (`duplicate_identity`, `erroneous_publication`, `takedown`). It writes no field
that a consumer could mistake for a statement about the norm. The two axes must not share
a field, and the ledger is the second axis.

### 3. No `VACUUM`, ever — so a retraction is undoable

A Delta `DELETE` is a new commit. The prior version stays readable via `DeltaTable(uri,
version=n)` and reversible via `DeltaTable(uri).restore(n)`, and the Parquet files survive
until vacuumed. Not vacuuming is what keeps a retraction undoable, so the retraction module
never offers one — and the ledger row carries the version number that makes the undo a
one-liner rather than an investigation.

This is deliberate about the `takedown` reason code too: a legal takedown that requires the
bytes to be *destroyed* is a separate, deliberate operation with its own authority trail,
not a flag on this job.

### 4. `processing_manifests` is never touched

The manifest records that a run produced an output. That happened. Deleting it would
falsify run history — the run journal would then claim a run produced nothing, which is
false in exactly the *absent-versus-broken* way #958 is about.

The manifest plus the retraction ledger together tell the whole story. A manifest whose
`published_document_ref` no longer resolves is not a dangling pointer to be tidied away; it
is **the intended signal**, and the ledger explains it. The retractor is structurally
incapable of touching the surface: it is never handed the URI.

### What is out of scope

Nothing here talks to OpenSearch. ADR-0005 makes the index a derived view, so the correct
sequence is: retract truth, then re-derive the view with
`document_intelligence_projection_reconcile`. The retraction job says so in its completion
log rather than doing it, because the two operations have different blast radii and
different approval requirements.

## Consequences

### A new canonical surface, and a new operator job

- `canonical_retractions` joins `SURFACE_DEFINITIONS`, so it is registered, contract-
  rendered into `dbt/models/sources_published.generated.yml`, and readable like any other
  surface. Its URI is derived from `DI_SURFACES_ROOT_URI`, or set explicitly with
  `DI_CANONICAL_RETRACTIONS_URI`.
- `document_intelligence_canonical_retract` is dry-run by default. Mutating requires an
  explicit `--retract`; `--reason-code`, `--reason` and `--retracted-by` are mandatory;
  `duplicate_identity` additionally requires `--superseded-by` naming a document that the
  job verifies still has a canonical row.
- The corpus-fraction bound defaults to **0.10**, an order of magnitude tighter than
  `projection_reconcile`'s 0.25, because a wrong de-index is repaired by a backfill and a
  wrong retraction is repaired only by a restore that someone has to notice is needed.
- An enumerated canonical side of **zero documents** is a refusal, not a permissive
  no-op: it reads as a misconfigured `DI_SURFACES_ROOT_URI`, not as an empty corpus.

### Every canonical string filter now goes through one helper

This was discovered by building the delete path, and would not have been reachable before
it. Once a Delta surface has had rows deleted, delta-rs rewrites the surviving rows through
a writer that materialises string columns as `string_view`, while the dataset schema still
reports `string`. A bare `pc.field("document_id") == some_str` then raises
`ArrowNotImplementedError: Function 'equal' has no kernel matching input types`, and
**every `document_id`-filtered read of that surface fails — not just the retracted row.**
The blast radius is the whole surface: document detail reads, the append path's revision
lookup, and the retractor's own resolution.

`persist.sinks.delta_string_equals` pins both sides to `string` and is now the only way
canonical reads build a string equality filter. Per ADR-0050 this is one rule with one
enforcement point; per ADR-0051 it ships with a test that fails when it is reverted — and
that test needs a fixture **large enough to reach the condition**. Measured on deltalake
1.6.3 / pyarrow 25.0.1, a two-row table with one row deleted does not reproduce the defect
and a six-row one does. The rescued code's own regression test used a two-row fixture and
therefore passed with the fix reverted; that is recorded here because a fixture calibrated
below the threshold is an abstention, not a pass.

### The reason vocabulary is closed on purpose

An operator who cannot classify a removal under `duplicate_identity`,
`erroneous_publication` or `takedown` does not yet understand it well enough to remove
canonical truth. Widening the vocabulary is an ADR-level change, not a flag.

### What this does not solve

Retraction removes a wrong record; it does not settle what a *right* record's identity is.
That is #850, and it should land first — reindexing before document identity is settled is
reindexing the wrong keys.

## References

- Issue #806 — the duplicate Bundesverfassung in the production index
- Issue #958 — the corpus states what is true, or refuses
- Issue #652 — the identity-key change that minted the duplicate
- [ADR-0005](0005-search-strategy.md) — the search index is a derived view
- [ADR-0033](0033-agentic-legal-reasoning.md) — a demo that lies convincingly is worse than one that fails
- [ADR-0038](0038-user-identity-and-operator-attribution.md) — operator attribution on state changes
- [ADR-0050](0050-one-rule-one-enforcement-point.md) — one rule, one enforcement point
- [ADR-0051](0051-a-gate-that-cannot-fail-is-not-a-gate.md) — a gate that cannot fail is not a gate
- [ADR-0052](0052-declared-means-produced.md) — declared means produced
