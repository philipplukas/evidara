# Document Intelligence

## Purpose

Turn immutable artifact bundles into canonical structured document intelligence. Document-intelligence transforms heterogeneous upstream content into stable `Document` and `Section` outputs, processing manifests, and published downstream surfaces.

## Current state

Contracts are defined, but the processing pipelines are not yet implemented.

## Source of truth

- Delta tables for canonical documents, sections, and processing manifests
- Published DI surfaces for downstream consumers
- Unity Catalog lineage for DI-internal job, table, and published-surface lineage
- Processing logic in Databricks workflows
- `contracts/schemas/document.schema.json`, `contracts/schemas/section.schema.json`, and `contracts/schemas/processing-manifest.schema.json`

## Responsibilities

### Minimal v1

- Read immutable artifact bundle manifests and artifacts
- Normalize and parse raw content
- Produce canonical `Document` and `Section` entities
- Assign `document_revision`
- Publish exact immutable downstream refs

Document-intelligence should lean on Databricks-native lineage for internal traceability, while still emitting Evidara contracts for any lineage or lifecycle state that must cross into other components.

### Boundary

- **Does own:** normalization, parsing, profile selection, canonical entities, document revisions, published surfaces, Databricks pipelines
- **Does NOT own:** source lifecycle, approvals, acquisition checkpoints, search projection logic

## Minimal next tasks

- [x] Define canonical `Document` schema
- [x] Define canonical `Section` schema
- [x] Define `ProcessingManifest` schema
- [ ] Define initial Delta table schemas and published views
- [ ] Define first Databricks workflow/job
- [ ] Define source/jurisdiction profile registry

## Minimal v1 Outcome

One bundle can be transformed into:

1. One or more canonical document revisions
2. Canonical sections from day one
3. Processing manifests with exact published refs
4. `document.processed` events emitted per document revision

## Later expansion

| Phase | Capability |
|-------|-----------|
| Next | Jurisdiction and authority resolution |
| Next | Citation extraction |
| Later | Optional OpenLineage export if cross-platform lineage becomes necessary |
| Later | Document relationships |
| Later | Quality scoring |
| Later | Richer profile registries and resolution audits |

## Dependencies

| Dependency | Purpose |
|-----------|---------|
| Databricks | Processing runtime and orchestration |
| Delta tables | Canonical and manifest storage |
| Unity Catalog lineage | DI-internal lineage and governance |
| GCS | Read raw artifacts and bundle manifests |
| Pub/Sub | Consume acquisition events, emit status and publication events |

## Key Contracts

- **Consumes:** `artifact_bundle.available`
- **Consumes:** reference snapshot sets published by platform-control
- **Produces:** `document.processing_status.updated`
- **Produces:** `document.processed`
- **Produces:** `document.withdrawn`
- **Schemas:** `Document`, `Section`, `ProcessingManifest`

## Testing

See [Document Intelligence Testing](testing/document-intelligence-testing.md) for the full testing strategy.

Key tests:

- Unit tests for parsing helpers and section construction
- Schema validation for `Document`, `Section`, and `ProcessingManifest`
- Golden document tests with representative bundles
- Invariant checks on provenance, revisions, and section ordering
- One minimal end-to-end processing path

## Drift risks

| Risk | Mitigation |
|------|-----------|
| Source format changes break parsing | Golden bundle tests detect regressions |
| Section structure changes unexpectedly | Invariant checks and section-count drift checks |
| Reference snapshot changes alter outputs unexpectedly | Record snapshot set refs in `ProcessingManifest` |
| Pipeline runs but publishes stale or partial data | Emit `document.processed` only after canonical-ready manifest state |
