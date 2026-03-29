# Document Intelligence

## Purpose

Turn raw artifacts into canonical structured document intelligence. Document-intelligence is the processing engine that transforms unstructured or semi-structured legal content into a well-defined canonical model stored in Delta tables.

## Current state

Not yet implemented. Repository scaffolding and component documentation exist. Contracts and schemas are planned but not yet defined.

## Source of truth

- Delta tables for canonical documents, sections, and citations
- Processing logic in Databricks workflows
- `contracts/schemas/document.schema.json` and `contracts/schemas/section.schema.json` for canonical entity shapes

## Responsibilities

### Minimal v1

- Load raw artifact from object storage
- Parse document content
- Produce canonical `Document` entity
- Optionally produce `Section` entities
- Store canonical results in Delta tables

### Boundary

- **Does own:** parsing, segmentation, canonical entities, Delta truth, Databricks pipelines
- **Does NOT own:** source lifecycle, approvals, search projections, run orchestration

## Minimal next tasks

- [ ] Define canonical `Document` schema (`contracts/schemas/document.schema.json`)
- [ ] Define minimal `Section` schema (`contracts/schemas/section.schema.json`)
- [ ] Define initial Delta table schemas
- [ ] Define first Databricks workflow/job
- [ ] Define input contract from platform-control (`raw_artifact.available`)
- [ ] Define output contract to legal-search (`document.processed`)

## Minimal v1 Outcome

A raw artifact can be transformed into:

1. One canonical document row in Delta
2. Basic section rows in Delta
3. Full lineage back to source → source_version → run → artifact

## Later expansion

| Phase | Capability |
|-------|-----------|
| Next | Jurisdiction assignment |
| Next | Citation extraction |
| Later | Document relationships |
| Later | Quality scoring |
| Later | Advanced section hierarchy |
| Later | Evidence refs |

## Dependencies

| Dependency | Purpose |
|-----------|---------|
| Databricks | Processing runtime and workflow orchestration |
| Delta tables | Canonical data storage |
| GCS | Read raw artifacts from object storage |
| Pub/Sub | Consume `raw_artifact.available`, emit `document.processed` |

## Technology

| Concern | Technology |
|---------|-----------|
| Processing | Databricks |
| Canonical Storage | Delta tables |
| Raw Input | GCS (object storage) |
| Orchestration | Databricks Workflows |

## Key Contracts

- **Consumes:** `raw_artifact.available` event from platform-control
- **Produces:** `document.processed` event
- **Schemas:** `Document`, `Section`, `Citation` (future), `EvidenceRef` (future)

## Testing

See [Document Intelligence Testing](testing/document-intelligence-testing.md) for the full testing strategy.

Key tests:

- Unit tests for parsing helpers and section construction
- Schema validation for `Document`, `Section`, `Citation`
- Golden document tests with 10–20 representative samples
- Invariant checks: lineage present, sections ordered, required fields populated
- One minimal end-to-end processing path

## Drift risks

| Risk | Mitigation |
|------|-----------|
| Source format changes break parsing | Golden document tests detect regressions |
| Section counts change unexpectedly | Distribution checks on average section count |
| Citation extraction degrades silently | Golden tests assert expected citation counts |
| Metadata null rates spike | Invariant checks for required fields |
| Processing runs but produces lower quality output | Golden comparison catches semantic drift |
