# Legal Search

## Purpose

Serve legal and document search and detail experiences to users. Legal-search is the user-facing serving layer that consumes published canonical surfaces from document-intelligence and turns them into OpenSearch projections and UI/API responses.

## Current state

The `legal-search/` folder contains:

- **Frontend (Next.js 16):** Full workspace UI with resizable panels, filter panel, result list, detail panel with tabs, mobile layout. 43 components using shadcn/radix primitives and a custom design system. Default runtime uses the live BFF via generated clients; e2e keeps an explicit mock mode for deterministic smoke checks.
- **BFF (NestJS):** Search and document detail endpoints wired to OpenSearch. Contract-first ViewModel mappers (ADR-0011, ADR-0012) with vocabulary-driven labels and observable fallbacks. 104 tests passing. Labels are in German (ADR-0013).
- **OpenSearch adapters:** Search with multi_match, faceted aggregations (jurisdiction, document type, language), highlight-based snippets. Document detail with sections and citations.
- **Seed pipeline:** Script to ingest Swiss court decisions from opencaselaw.ch into a local OpenSearch index.
- **Contracts:** OpenAPI spec, search projection schema with provenance, controlled vocabularies for jurisdiction and document type.

The frontend is connected to the live BFF using generated API clients. Projection ingestion endpoints for `document.processed` and `document.withdrawn` are implemented, with idempotency and revision-order checks in the projection history layer.

## Source of truth

- Published canonical surfaces from document-intelligence are read-only inputs
- OpenSearch holds serving projections only
- `contracts/api/legal-search.openapi.yaml` defines the user-facing API
- `contracts/api/document-intelligence.openapi.yaml` defines the **Document Service** calls the BFF uses for document body reads (ADR-0010); configure `DOCUMENT_INTELLIGENCE_BASE_URL` in `legal-search/api` (see `.env.example`)

## Responsibilities

### Minimal v1

- Build search projections from published DI surfaces
- Maintain OpenSearch indices and aliases
- Maintain projection manifest/history for replay and audit
- Expose search and detail APIs
- Serve a minimal frontend search experience

### Boundary

- **Does own:** frontend, BFF, projection logic, OpenSearch mappings and aliases, indexing workflows
- **Does NOT own:** canonical truth, source management, parsing, reference data governance

## The hierarchy of norms

`GET /v1/norm-hierarchy/{jurisdiction_id}` answers *what governs this place, at each
level* — the traversal ADR-0033 builds the agentic layer on. It is not a search: the
governing chain is derived from the jurisdiction tree, not from text similarity.

**Where each piece comes from.** platform-control owns the jurisdiction tree and each
jurisdiction's `level` (`constitutional` / `international` / `federal` / `cantonal` /
`municipal` — ranked in `contracts/vocabularies/norm-level.json`). legal-search must not
call platform-control at request time for reference data that cannot change between
deploys, so the tree is **exported at build time** by
`scripts/generate_jurisdiction_hierarchy_vocab.py` into
`contracts/vocabularies/jurisdiction-hierarchy.json` and loaded like any other
vocabulary. CI fails if the export drifts from the seed.

**What the projection derives** (`core/norm-hierarchy`, applied in
`ProjectionsService.buildProjection`):

| Field | Derived how |
|---|---|
| `level` | From the document's **jurisdiction**, never guessed from its text. Most specific jurisdiction wins. A document may declare `constitutional` for itself — the one level no jurisdiction can supply, since the BV is enacted by `jur_ch_federal` exactly like the TSchG. A declared level that would *demote* the norm is ignored. |
| `subordinate_to` | The jurisdictions whose law outranks it. A Zurich communal ordinance → `jur_ch_zh`, `jur_ch_federal`. The edge points at **scopes, not documents**: subordination in law is scope-wide, so a document→document edge would be a fiction. |
| `in_force_from` / `in_force_until` | `in_force_from` coalesces `effective_date`, so there is one field to range-query. `in_force_until` is the **last date the norm WAS in force** (inclusive). |
| `delegates_to` | **Not derived — unpopulated.** Delegation is an assertion made *by a norm's text* (the cantonal clause that lets a commune legislate at all), so it needs extraction or curation. The shape is declared in `contracts/schemas/document.schema.json` so the edge has a home. |

**Why `jur_ch_federal` is reachable from a canton.** In the seed, `jur_ch_federal` is a
*child* of `jur_ch`, and the cantons are its *siblings* — so walking parents alone would
never reach federal law from Zurich, and preemption would be unanswerable. The rule is
therefore: the scopes governing a jurisdiction are its ancestors, **plus each ancestor's
children at the same level**. A same-level child is a refinement of its parent's scope,
not a tier beneath it.

**Temporal validity is four-valued, not boolean.** `in_force_state` is `in_force`,
`not_yet_in_force`, `repealed`, or `unknown`. A norm marked `repealed` with no date
resolves to `unknown` — inventing `in_force` from a missing field is the confident
fabrication the platform exists to prevent. `in_force_at` filtering excludes only norms
*known* to be outside force; unknown-dated norms are kept and flagged, because dropping
them would hide law and silence is indistinguishable from absence.

**Coverage is load-bearing.** `coverage.missing_levels` names the levels that bind a
place but for which the corpus holds nothing. "I do not have the communal ordinance for
this place" is a correct answer (ADR-0033 §2); reasoning past a missing level is not.

## Corpus coverage

`GET /v1/coverage` (ADR-0042) answers *what do we hold for this scope* — grouped by
jurisdiction, authority, document type or norm level, optionally as of a date. It exists
because `coverage.missing_levels` above, while real, is **level-granular**, and the
failure it must prevent is instrument-granular: in the M13 iteration-2 measurement the
federal level was covered by the Bundesverfassung while TSchG and TSchV were absent, so
`missing_levels` was correct and silent about the only thing that mattered (#709).

**What it may be read to mean.** `holding: not_held` means *the search index contains no
document matching this scope*. It is a claim about our holdings, in the first person. It
is **not** a claim that the norm does not exist. The enum has exactly two members —
`held` and `not_held` — precisely so no caller can find a value meaning "confirmed absent
in law", and no such value will be added. The corpus is a subset of the law by
construction; no endpoint over it can be evidence of what the law does not contain. The
strongest claim it supports is a refusal, which per ADR-0033 §2 is a *correct* answer.

**Absence is reported, not inferred.** A terms aggregation produces no bucket for a value
absent from the index, so a jurisdiction the caller names explicitly always comes back as
a group — `documents: 0, holding: not_held` when we hold nothing. That positive statement
of absence is the point; without it a caller is back to inferring absence from emptiness,
which #672 showed is one filter bug away from being wrong.

**An unrecognized id is not a coverage answer.** A jurisdiction id the platform does not
know produces no group and is listed in `unrecognized_jurisdiction_ids`. Answering "we
hold nothing for `jur_ch_zurich`" would read as a coverage fact when the truth is that
the caller misspelled `jur_ch_zh`.

**Freshness is not currency.** `last_processed_at` is when the newest document in the
group entered the corpus — *not* when the source was last checked, and therefore not
evidence that no newer law exists. A jurisdiction whose law changed last week and whose
last acquisition ran a year ago reports a year-old timestamp with no staleness signal.
"When did we last check?" is run history, and it lives in platform-control (ADR-0042 §4).

**No completeness score.** "We hold 41 federal acts" is not "we hold all federal acts".
Nothing in the platform knows the denominator, so no percentage is reported; inventing
one would be the most dangerous field this endpoint could carry.

**Deployment note.** `level`, `subordinate_to`, `in_force_from` and `in_force_until` are
new mapping fields. Documents indexed before this change carry none of them and will not
appear in any level bucket until reprojected — see
`docs/runbooks/projection-reindex-backfill.md`.

## Minimal next tasks

- [x] Define search projection schema
- [x] Define minimal NestJS BFF endpoints
- [x] Connect frontend to live BFF (replace mock data with Orval-generated client)
- [x] Define initial OpenSearch mapping and alias strategy
- [x] Define projection manifest/history model
- [x] Implement `document.processed` ingestion and projection writer (consume events, read published refs, transform to projection schema, upsert to OpenSearch)
- [x] Implement `document.withdrawn` ingestion and deindex/tombstone behavior, including replay ordering tests
- [x] Define reindex workflow
- [x] Internationalization: BFF locale-awareness and frontend `next-intl` (ADR-0013, Phases 1–2)

## Minimal v1 Outcome

A user can:

1. Search documents by text
2. Open a document detail page
3. Filter by a small set of metadata fields

## Later expansion

| Phase | Capability |
|-------|-----------|
| Next | Section-level search |
| Next | Citation-aware search |
| Next | i18n: French and Italian UI (ADR-0013) |
| Next | Five-country content overlays (CH/AT/DE/FR/IT) for consistent filter and detail semantics |
| Later | Facets and ranking improvements |
| Later | Per-language OpenSearch analyzers |
| Later | Semantic search |
| Later | Richer document exploration |

Content scaling reference:

- `docs/components/five-country-content-rollout.md`
- `legal-search/frontend/docs/multi-country-content-spec.md`

## Dependencies

| Dependency | Purpose |
|-----------|---------|
| OpenSearch | Search index and query engine |
| Published DI surfaces | Projection input |
| Pub/Sub | Consume `document.processed`, `document.withdrawn`, and `index_update.requested` |
| Cloud Run | Runtime for BFF and frontend |

## Platform Capabilities We Reuse

- Versioned physical indices plus aliases for zero-downtime cutover
- Bulk indexing APIs for replay and rebuild

These replace the need for custom index-lifecycle semantics in shared contracts. The shared contracts only need to carry projection inputs, ordering, and withdrawal signals.

## Key Contracts

- **Consumes:** `document.processed`
- **Consumes:** `document.withdrawn`
- **Consumes:** `index_update.requested`
- **API:** `contracts/api/legal-search.openapi.yaml`
- **Reads:** published DI surfaces referenced by event refs

## Citation graph

Per [ADR-0033](../adr/0033-agentic-legal-reasoning.md), legal reasoning is *traversal*, not
similarity: "RAG to enter, graph to reason." The citation graph is what steps 3–4 of that
workflow walk, and it lives in two OpenSearch indices, both with a managed mapping in
`legal-search/api/src/core/opensearch/citation-graph-index.mapping.ts` and bootstrapped on
startup (`citation-graph-bootstrap.ts`):

| Index | Role | Written by |
|---|---|---|
| `citations` | **Edges.** One row per citation string found in a document, carrying `normalized_reference` — the canonical `{type}:{value}` key (`sr:210`) that DI's `normalize_citation()` emits. | `ProjectionsService.extractCitations` |
| `citation-targets` | **Nodes.** One row per identifier a document *is* — `sr:101` is the Bundesverfassung. | `ProjectionsService.extractCitationTargets` |

An edge exists when a citation's key matches a target's key. That join is the entire graph.

**Where a document's own identifier comes from.** The Fedlex SPARQL provider emits a title,
a short title and an ELI URI — but no SR number. So a Swiss federal law declares its SR
number only in its **masthead**: the raw title (`Bundesverfassung ... (SR 101)`) and the
opening line of the body (`Vom 18. April 1999 (Stand am 1. Januar 2024), SR 101.`). Target
extraction therefore scans the raw (un-normalized) title, plus a bounded masthead window of
the body, and only for `document_type: law`. The bound is deliberate: an SR number past the
masthead is a citation to a *different* norm, and letting a decision register itself as
`sr:210` would make every citation of the civil code in the corpus resolve to it. **A wrong
edge is worse than a missing one.**

**Traversal is keyed, not denormalized.** `GET /v1/citations/citing` joins on the canonical
key, not on the `target_document_id` written onto a citation at projection time. That field
is only set if the cited document already existed when the citing document was projected —
so a graph traversed through it silently loses every edge whose endpoints arrived in the
wrong order. (`GET /v1/documents/{id}/cited_by` still reads `target_document_id`, and is
correspondingly order-dependent.)

**The resolution rate is part of the contract.** `GET /v1/citations/stats` reports what
share of extracted citations actually resolve, and attributes the remainder:

- `not_normalizable` — DI could not key the citation at all (a fuzzy form like `Art. 36 BV`).
  An **extractor** gap.
- `unresolved_target` — the key is valid but names a norm not in the corpus. A **coverage** gap.

These are reported rather than hidden because an unresolved citation is a *broken edge*, and
consumers read a missing edge as "no such relation exists" (see [ADR-0032](../adr/0032-pipeline-observability.md)).
The same numbers are exported as Prometheus metrics (`legal_search_citation_resolution_rate`,
`legal_search_citations_projected_total{keyed}`) and alerted on in
`infra/hetzner/observability/alerts.yaml` (`evidara.citation-graph`).

**Known gap:** bare article references (`Art. 36 BV`) are the dominant citation form and are
*not* resolved — they need search-based resolution against article-level sections, which
depends on article-level sectioning. They are counted as `not_normalizable`, never guessed.

## Operator references

- `docs/runbooks/projection-reindex-backfill.md` — alias-cutover reindex pattern.
- `docs/runbooks/staging-projection-replay.md` — projection replay against staging.
- `docs/runbooks/hitl-rollout.md` — HITL rollout (canonical `jur_*`/`auth_*` filters, commentary records, mapping change + replay).

## Testing

See [Legal Search Testing](testing/legal-search-testing.md) for the full testing strategy.

Key tests:

- Projection builder unit tests
- Search and detail API contract tests
- Indexing smoke test with sample docs
- Fixed search smoke queries
- Parity checks between published DI surfaces and indexed documents

## Drift risks

| Risk | Mitigation |
|------|-----------|
| Search index diverges from canonical data | Projection manifest/history and parity checks |
| Projection logic drops fields | Projection builder unit tests |
| Search serves a withdrawn document | Withdrawal event tests and alias-safe replay |
| Out-of-order events overwrite fresh data | `document_revision` ordering checks |
