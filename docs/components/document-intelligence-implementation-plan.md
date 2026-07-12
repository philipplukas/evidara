# Document Intelligence Implementation Plan

## Status

In progress. This document describes the intended architecture and delivery plan for `document-intelligence`. Current reality remains documented in `document-intelligence.md`.

## Purpose

Define the planned architecture, delivery phases, documentation updates, and testing strategy for implementing the `document-intelligence` component.

## Current state

`document-intelligence` is not production-implemented yet. Contracts and component docs exist, and the current scaffold now includes bundle-based event intake, local and GCS bundle reads, HTML-first plus initial XML canonicalization, Delta-backed published-surface writes, explicit surface definitions, offline contract validation helpers, a Databricks runtime entrypoint, Databricks Asset Bundle scaffolding, a reusable Terraform module plus top-level Databricks stack and per-environment tfvars for Unity Catalog scaffolding, SQL/bootstrap assets for published-surface registration, a dedicated component quality gate in CI, and golden/adapter/CLI tests. Spark-native runtime wiring, deploy/promotion integration for Terraform + Bundles, broader XML coverage, citations, and jurisdiction resolution still need to be created.

## Goal

Deliver the minimal `document-intelligence` component for Milestone M2 and connect it into the first end-to-end slice for Milestone M4.

The first implementation must:

1. Consume `artifact_bundle.available`
2. Read an immutable bundle manifest and its artifacts from object storage
3. Normalize and parse document content
4. Produce canonical `Document`, `Section`, and `ProcessingManifest` records with provenance
5. Persist canonical truth and published surfaces in Delta
6. Emit `document.processing_status.updated` and `document.processed`
7. Ship with sufficient documentation and tests to support safe iteration

## Planning Assumptions

- `contracts/` is the highest-authority definition for schemas and events.
- `platform-control` owns connectors, source lifecycle, runs, approvals, and reference data.
- `document-intelligence` begins at the artifact-bundle boundary and does not fetch upstream sources directly.
- Delta is canonical truth. Search-serving projections are downstream and owned by `legal-search`.
- Sections are part of MVP. The first release should not treat section extraction as optional.
- Citation extraction and jurisdiction assignment remain post-MVP unless contracts are deliberately expanded.
- The first supported source family should be narrow, ideally HTML or the earliest real source family selected for the vertical slice.
- All implementation is authored fresh for this repository, starting from the requirements and contracts documented here.

## Source of truth

- Delta tables for canonical processed output
- `contracts/events/artifact-bundle-available.schema.json` for inbound event shape
- `contracts/events/document-processing-status-updated.schema.json` and `contracts/events/document-processed.schema.json` for outbound event shapes
- `contracts/schemas/document.schema.json`, `contracts/schemas/section.schema.json`, and `contracts/schemas/processing-manifest.schema.json` for canonical entity contracts
- This plan for intended future-state implementation sequencing

## MVP Scope

### In scope

- One supported source family
- `artifact_bundle.available` event consumption
- Bundle-manifest and artifact retrieval from GCS
- Content normalization and body extraction
- Flat ordered section extraction
- Canonical `documents` and `sections` Delta tables
- Processing manifest / readiness tracking
- `document.processing_status.updated` and `document.processed` event emission
- Contract, component, and testing documentation updates
- Unit, contract, golden, invariant, and minimal integration tests

### Out of scope

- Exhaustive PDF or Office document support
- Advanced nested section hierarchy
- Citation extraction beyond scaffolding
- Canonical jurisdiction assignment beyond source-level hints
- Embeddings and commentary generation
- Search-serving projections
- Performance optimization beyond basic correctness and reliability

## Minimal next tasks

- [ ] Confirm the first source family for MVP
- [ ] Reconcile the current `Document`, `Section`, and `ProcessingManifest` expectations
- [x] Create the `document-intelligence/` component scaffold
- [x] Adapt the scaffold to `artifact_bundle.available` and bundle-manifest intake
- [x] Implement event intake plus bundle-manifest and artifact reads
- [x] Implement `Document` plus `Section` canonicalization
- [x] Add manifest readiness plus status/publication events
- [x] Land the first unit, contract, golden, invariant, and integration tests
- [x] Add local Delta-backed persistence adapters and GCS-backed read adapters
- [x] Define initial published surface schemas explicitly
- [x] Add Databricks workflow packaging and runtime wrapper
- [x] Add Terraform and SQL/bootstrap scaffolding for Unity Catalog published-surface registration
- [x] Add XML-first second source family support
- [ ] Integrate Terraform + Asset Bundle deployment into CI/CD and environment promotion

## Target Architecture

## Boundary With Platform Control

`platform-control` remains the entry point for all new data entering the system. It owns sources, corpora, source versions, runs, source snapshots, artifact registration, and bundle manifests. Connector execution belongs to that component, even if connectors run as separate workers or jobs.

`document-intelligence` consumes only the handoff contract:

- `artifact_bundle.available` event
- immutable bundle manifest in object storage
- sibling artifacts in object storage
- provenance, trust tier, and source-origin metadata from the producing run

The first implementation can still optimize for bundles with one primary document artifact, but the runtime should follow bundle semantics from day one rather than pretending every upstream item is a single file.

## Interaction With Platform Control

## Control-Plane Responsibilities

`platform-control` should own the upstream-facing lifecycle:

- define sources
- define source versions
- store connector configuration
- trigger and track runs
- register source snapshots and artifacts
- write immutable bundle manifests
- store reference data such as jurisdictions and authorities
- emit `artifact_bundle.available`

`document-intelligence` should not:

- call upstream APIs directly as part of normal processing
- scrape sources directly
- own run orchestration
- mutate `platform-control` tables directly

## Planned Handoff Sequence

The recommended happy-path interaction is:

1. A source is created in `platform-control`.
2. A source version is created in `platform-control` with the frozen connector configuration for that source.
3. A run is triggered in `platform-control`, either manually, by schedule, or by a repair workflow.
4. A connector worker owned by `platform-control` fetches upstream content.
5. The connector worker writes one or more raw artifacts to GCS.
6. `platform-control` records the source snapshot, artifact metadata, and provenance.
7. `platform-control` writes an immutable artifact bundle manifest that captures provenance, parser hints, source defaults, reference-context policy, and artifact refs.
8. `platform-control` emits `artifact_bundle.available` only after the bundle manifest is durably stored and registered.
9. `document-intelligence` consumes the event and validates the payload against the contract.
10. `document-intelligence` reads the bundle manifest and referenced artifacts from GCS and starts canonical processing.
11. `document-intelligence` writes canonical `documents`, `sections`, and `processing_manifest` rows plus published-surface refs.
12. `document-intelligence` emits `document.processing_status.updated` during processing and `document.processed` only after the manifest reaches `canonical_ready`.
13. `platform-control` consumes status feedback for run tracking and operational visibility.

## Data Handoff Semantics

The physical handoff is:

- bundle manifest in GCS
- referenced sibling artifacts in GCS
- event in Pub/Sub

The logical handoff is:

- provenance owned by `platform-control`
- immutable reference to the bundle manifest
- trust-tier, source-origin, parser-hint, and reference-context inputs for DI resolution

The canonical handoff back out of `document-intelligence` is:

- canonical IDs owned by `document-intelligence`
- Delta-backed processed records
- `document.processed` event for downstream consumers

No component should read another component's operational database directly. Cross-component interaction must happen through contracts, events, or explicitly defined APIs.

## Source Version And Connector Configuration

For planning purposes, each `source_version` in `platform-control` should freeze the acquisition configuration that produced a given run.

Recommended contents of source-version-owned connector configuration:

- connector type
- root URL or API endpoint
- authentication reference
- pagination or cursor strategy
- rate-limit settings
- parser hints
- source defaults such as jurisdiction or authority hints
- extraction selectors or mapping configuration

This allows `document-intelligence` to trust lineage and source context without needing to understand how the upstream fetch was performed.

## Success Feedback To Platform Control

`document-intelligence` should report processing outcomes back to `platform-control` so runs can be observed operationally.

The first implementation may do this through:

- asynchronous processing-status events
- or a minimal callback/status API if later needed

Minimum useful status outcomes:

- accepted
- processing
- canonical_ready
- failed
- withdrawn
- skipped_duplicate

Each status update should include:

- `processing_manifest_id`
- `provenance`
- processing version
- status
- optional `document_id` and `document_revision`
- optional error code
- optional error summary

## Failure And Replay Behavior

Failure and replay behavior should be explicit at the boundary.

Recommended rules:

- if bundle-manifest registration fails, `platform-control` does not emit `artifact_bundle.available`
- if `document-intelligence` receives the same bundle twice for the same processing version, it should behave idempotently
- if parsing fails, `document-intelligence` should record the failure and surface it back to `platform-control`
- reprocessing should happen by triggering a new run or by replaying a bundle with a new processing version, not by ad hoc database mutation
- downstream systems should trust readiness state and processed events, not partially written canonical rows

## Near-Term Contract Gaps

The current contract model is much stronger than the earlier placeholder boundary, but a few implementation choices should still stay flexible.

Likely future additions:

- richer bundle composition beyond one primary document artifact
- more explicit publication and withdrawal operational procedures
- profile registries and resolution-policy governance
- richer failure taxonomies and repair semantics

## Internal Pipeline Stages

1. Event intake and validation
2. Idempotency check on bundle manifest plus processing version
3. Bundle-manifest read, artifact selection, and content-type dispatch
4. Source normalization
5. Body extraction and cleanup
6. Sectionization
7. Canonical entity construction
8. Delta persistence and published-surface write
9. `ProcessingManifest` update
10. `document.processing_status.updated` emission
11. `document.processed` emission
12. Failure reporting

## Recommended Component Structure

```text
document-intelligence/
  README.md
  pyproject.toml
  src/document_intelligence/
    config/
    contracts/
    ingest/
    normalize/
    parsers/
    sectionize/
    canonical/
    persist/
    events/
    quality/
    jobs/
  tests/
    unit/
    contract/
    integration/
    golden/
  databricks/
    workflows/
    jobs/
```

This structure is a recommendation for implementation, not current state.

## Data Model Plan

## Layering

### Bronze / Raw

Used for ingestion bookkeeping and reproducibility.

- artifact manifests
- raw extracted text snapshots if needed
- parser diagnostics
- optional normalized intermediate records

### Silver / Canonical

Canonical source of truth for processed content.

- `documents`
- `sections`
- `processing_manifest`
- `processing_failures`
- optional `metadata_candidates`

### Gold / Internal

Optional internal marts only.

- quality summaries
- drift metrics
- analyst-friendly operational aggregates

Search-serving projections do not belong here. They remain downstream in `legal-search`.

## Canonical Tables

### `documents`

Initial planned fields:

- `document_id`
- `document_revision`
- `processing_manifest_id`
- `provenance`
- `primary_artifact_id`
- `title`
- `full_text`
- `body_text`
- `document_type`
- `processed_at`
- `processing_version`
- `lifecycle_status`
- `metadata`
- `extensions`

Planned additions after MVP:

- `jurisdiction_id`
- `authority_id`
- `effective_date`
- richer document relationships

### `sections`

Initial planned fields:

- `section_id`
- `document_id`
- `document_revision`
- `processing_manifest_id`
- `provenance`
- `parent_section_id`
- `ordinal`
- `depth`
- `title`
- `content`
- `section_type`
- `metadata`

The first release should support flat ordered sections. `parent_section_id` and `depth` may remain simple until hierarchical extraction is implemented.

### `processing_manifest`

This table exists to give downstream consumers a safe readiness signal in a multi-table write model.

Planned fields:

- `processing_manifest_id`
- `manifest_version`
- `document_id`
- `document_revision`
- `provenance`
- `input_bundle_manifest_ref`
- `processing_version`
- `status`
- `selected_profiles`
- `reference_snapshot_set_ref`
- `published_document_ref`
- `published_sections_ref`
- `canonical_ready_at`
- `supersedes_processing_manifest_id`
- `document_count`
- `section_count`
- `citation_count`
- `failure`

`document.processed` should only be emitted after the canonical writes are complete and the manifest is marked ready.

## Jurisdiction And Reference Data Plan

Jurisdictions and authorities are owned by `platform-control`, not `document-intelligence`.

Implementation implications:

- Bootstrap reference data may begin as seeds for development.
- Long-term authoritative reference data should live in `platform-control`.
- `document-intelligence` should consume mirrored or exported reference tables for lookups.
- The MVP pipeline may preserve source-level jurisdiction hints in metadata without promoting them to canonical truth.

Recommended jurisdiction model for later phases:

- adjacency list as source of truth
- path or ancestor representation for efficient downstream joins
- stable `jurisdiction_id` carried into canonical entities once assignment is implemented

## Parsing, NLP, And Transformation Strategy

## Source Family Strategy

Start with one real source family only. Avoid building a generic parser framework before the first source family works end to end.

## Docling

Docling may be used as an internal normalization representation for PDF, HTML, DOCX, or mixed-content documents. It should not become the cross-component public contract.

## spaCy

spaCy is appropriate for early deterministic processing:

- heading detection support
- rule-based extraction
- citation pattern scaffolding
- text cleanup support

Use batched Python processing, not row-by-row UDF logic as the default implementation path.

## dbt

Use dbt for:

- seeds
- SQL transformations after Python parsing
- incremental canonical shaping where useful
- tests and documentation
- internal QA / ops marts

Do not use dbt as the primary home for:

- connectors
- parsing
- scraping
- main NLP execution

## Orchestration Plan

For MVP, keep orchestration simple:

- `platform-control` triggers and records runs
- Databricks executes `document-intelligence`
- Python tasks perform parsing and canonical construction
- dbt tasks may run after canonical writes for validation or lightweight downstream shaping

Do not add Dagster for the first implementation unless a new ADR justifies the complexity.

## Dependencies

| Dependency | Purpose |
|-----------|---------|
| Databricks | Runtime for parsing, canonicalization, and Delta writes |
| Delta tables | Canonical processed storage |
| GCS | Bundle-manifest storage and artifact retrieval |
| Pub/Sub | `artifact_bundle.available` consumption and status/publication emission |
| platform-control | Source lifecycle, runs, connectors, and reference data ownership |
| dbt | SQL shaping, tests, seeds, and internal marts after Python parsing |

## Phased Delivery Plan

## Phase 0: Contract And Documentation Alignment

### Deliverables

- Reconcile component doc current state with existing contracts
- Resolve MVP contract gaps across prose, schemas, and testing docs
- Publish this implementation plan
- Decide the first supported source family

### Documentation

- Update `docs/components/document-intelligence.md`
- Update `docs/components/testing/document-intelligence-testing.md`
- Update boundary docs if contract changes are made

### Tests

- Contract schema validity checks
- Example payload validation for `artifact_bundle.available`, `document.processing_status.updated`, and `document.processed`

## Phase 1: Component Scaffold

### Deliverables

- Create package structure under `document-intelligence/`
- Add config loading and job entrypoint stubs
- Add local development README
- Add Databricks workflow placeholders

### Documentation

- `document-intelligence/README.md`
- local development/setup notes if needed

### Tests

- import smoke tests
- basic configuration tests

## Phase 2: Inbound Processing Boundary

### Deliverables

- `artifact_bundle.available` consumer
- CloudEvents envelope validation
- bundle-manifest reader from GCS
- sibling-artifact reader from GCS
- idempotency handling
- structured processing logs

### Documentation

- inbound flow and failure-handling notes in component README or plan follow-up docs

### Tests

- event payload validation
- bundle-manifest reader unit tests
- artifact selection unit tests
- idempotency tests

## Phase 3: Normalization And Section MVP

### Deliverables

- first source-family parser
- body extraction
- title extraction
- flat ordered sectionization
- canonical document and section builders

### Documentation

- parser assumptions and known limitations
- source-family support notes

### Tests

- unit tests for normalization helpers
- unit tests for sectionization
- golden tests for 10 to 20 representative documents

## Phase 4: Canonical Persistence And Readiness

### Deliverables

- Delta table definitions for `documents`, `sections`, and `processing_manifest`
- write path with lineage propagation
- readiness update logic
- failure capture in `processing_failures`

### Documentation

- canonical table definitions
- manifest and readiness semantics

### Tests

- schema conformance tests
- invariant tests
- persistence integration tests

## Phase 5: Outbound Eventing And Status Feedback

### Deliverables

- `document.processing_status.updated` emission
- `document.processed` emission
- processing failure reporting
- processing version semantics

### Documentation

- event examples
- processing-state notes

### Tests

- `document.processing_status.updated` schema validation
- `document.processed` schema validation
- duplicate-event handling tests
- failure-path tests

## Phase 6: Vertical Slice Integration

### Deliverables

- one source family wired through `platform-control`
- canonical output in Delta
- `document.processed` consumed downstream
- happy-path and broken-path slice verified

### Documentation

- first operational runbook once procedures can be verified
- update milestone docs if the slice changes implementation details

### Tests

- minimal end-to-end slice
- broken-path visibility test

## Documentation Workstream

Documentation should land with each phase, not after implementation is complete.

Required documentation updates across the implementation:

- Component current-state doc
- This plan document
- Component testing guide
- Contract examples and boundary docs when contracts change
- Setup docs if local or Databricks workflows change
- Runbooks once operational procedures are stable enough to verify

## Testing Workstream

## Test Categories

### Contract tests

- JSON Schema validation
- example payload validation
- event contract regression checks

### Unit tests

- content-type detection
- normalization helpers
- title extraction
- section ordering
- empty-section handling

### Golden tests

- one representative set per source family in scope
- structure-focused assertions rather than exact text snapshots

### Invariant tests

- lineage fields present
- sections attached to valid document IDs
- section ordinals monotonic
- required contract fields populated

### Integration tests

- bundle-manifest read to canonical write
- Delta persistence
- event emission

### End-to-end tests

- first vertical slice happy path
- broken path with surfaced failure

## Test Data Plan

Golden fixtures should live under the component test area and follow the shared golden-dataset guidance.

Recommended layout:

```text
document-intelligence/tests/golden/
  inputs/
  expected/
  README.md
```

## Documentation And Testing Gates Per Milestone

## M2 Exit Criteria

- One supported source family works end to end inside `document-intelligence`
- Canonical `documents` and `sections` are written to Delta
- Provenance is preserved through the shared `provenance` block and primary artifact references
- `document.processed` is emitted only after readiness is marked
- Component docs and testing docs are updated in the same PR series
- Unit, contract, golden, invariant, and minimal integration tests are green

## M4 Exit Criteria

- `platform-control` emits `artifact_bundle.available`
- `document-intelligence` processes the bundle
- `legal-search` receives the downstream signal and indexes the result
- Search and detail views can display the processed document
- Broken-path behavior is visible and not silently swallowed

## Later expansion

| Phase | Capability |
|-------|-----------|
| Next | Citation extraction and citation schema activation |
| Next | Canonical jurisdiction assignment using mirrored reference data |
| Later | Hierarchical sections beyond flat ordered sections |
| Later | Richer artifact-bundle handling beyond a single primary document artifact |
| Later | Additional source families such as PDF and structured API-first sources |
| Later | Embeddings or AI-generated enrichment in non-canonical tables |

## Open Decisions

- Whether the first supported source family is HTML or another real upstream
- Whether `document_type` remains optional in MVP or is promoted earlier
- How aggressively the first runtime should support bundles with multiple primary-relevant artifacts
- When jurisdiction assignment should move from hint storage to canonical field population

## Drift risks

| Risk | Mitigation |
|------|-----------|
| Contracts, component docs, and testing docs drift apart | Update all related docs in the same PR series and keep `contracts/` authoritative |
| MVP scope grows to include too many source families or NLP features | Freeze one source family and one canonical path before expanding |
| Canonical tables become hard to consume due to partial multi-table writes | Use `processing_manifest` readiness semantics and gate outbound events on readiness |
| Jurisdiction/reference logic leaks into the wrong component | Keep authority and jurisdiction master data in `platform-control` and consume mirrored reference data only |
| dbt becomes the primary home of parsing logic | Keep parsing and NLP in Python jobs, and reserve dbt for SQL shaping, tests, and marts |

## Immediate next steps

1. Confirm the first source family for MVP
2. Reconcile the current `Document`, `Section`, and `ProcessingManifest` expectations
3. Adapt the existing component scaffold to the bundle-manifest boundary
4. Implement event intake plus bundle-manifest and artifact reads
5. Implement document plus section canonicalization
6. Add manifest readiness plus status and publication events
