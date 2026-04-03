# Document Intelligence

## Purpose

Turn immutable artifact bundles into canonical structured document intelligence. Document-intelligence transforms heterogeneous upstream content into stable `Document` and `Section` outputs, processing manifests, and published downstream surfaces.

## Current state

Initial implementation scaffolding now exists under `document-intelligence/`. The component now has a Python package skeleton, tolerant inbound event parsing, file-based intake for both raw `artifact_bundle.available` events and Pub/Sub push envelopes, bundle-manifest and artifact loading for local files and `gs://`, minimal HTML and XML normalization with shared-IR section extraction, explicit published-surface definitions, an in-memory sink plus a Delta-backed sink, offline JSON Schema validation helpers, a Databricks runtime entrypoint, Databricks Asset Bundle files with tracked `dev` / `staging` / `prod` targets, a reusable Terraform module plus top-level Databricks stack and `dev` / `staging` / `prod` tfvars for Unity Catalog scaffolding, SQL/bootstrap assets for published-surface registration, a dedicated local quality gate under [`../../scripts/check-document-intelligence.sh`](../../scripts/check-document-intelligence.sh), a runtime/deployment validation script under [`../../scripts/check-document-intelligence-runtime.sh`](../../scripts/check-document-intelligence-runtime.sh), and component CI coverage in GitHub Actions for linting, regression tests, and Terraform validation.

For the current M4 slice, freeze the primary happy path on Firecrawl-acquired HTML bundles with one primary document artifact. The existing RIS-style XML path remains useful regression coverage, but it is not the required deployment path for the first end-to-end searchable slice.

The production processing pipelines are still not fully implemented. Always-on Pub/Sub runtime wiring, YAML policy resolution, spaCy or comparable NLP stages, Docling-based structured extraction, Spark-native runtime execution, deploy/promotion execution for Terraform + Databricks Bundles, richer XML source-family coverage, citation extraction, jurisdiction resolution, and stricter final contract hardening are still pending.

See [Document Intelligence Implementation Plan](document-intelligence-implementation-plan.md) for the planned architecture and phased delivery approach.

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
- [x] Land initial local Python scaffold under `document-intelligence/`
- [x] Adapt the scaffold from the earlier single-artifact intake to `artifact_bundle.available` plus immutable bundle manifests
- [x] Implement GCS-native bundle-manifest and artifact reads
- [x] Implement Delta-backed canonical persistence and published-surface writes
- [x] Implement `document.processing_status.updated` and `document.processed` emission against the settled contracts
- [x] Add schema validation, golden bundles, and adapter/CLI tests
- [x] Define initial published surface schemas explicitly
- [x] Define first Databricks workflow/job scaffold
- [x] Add Terraform and SQL/bootstrap scaffolding for Unity Catalog published-surface registration
- [x] Add an XML-first second source family with RIS-style fixture coverage
- [ ] Add always-on runtime wiring for `artifact_bundle.available` consumption
- [ ] Define source/jurisdiction profile registry
- [ ] Harden HTML parsing and broaden source-family support deliberately

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
- **Planned next:** `document.withdrawn`
- **Schemas:** `Document`, `Section`, `ProcessingManifest`

## Testing

See [Document Intelligence Testing](testing/document-intelligence-testing.md) for the full testing strategy.

Key tests:

- Unit tests for parsing helpers and section construction
- Offline JSON Schema validation for `Document`, `Section`, `ProcessingManifest`, and current event contracts
- Golden document tests with representative bundles
- GCS loader tests with stubbed storage client behavior
- Delta sink tests with real local Delta tables
- CLI smoke test for bundle processing
- Pub/Sub push-envelope decoding tests for both processing entrypoints
- Databricks runtime wrapper and bundle-config tests
- Invariant checks on provenance, revisions, and section ordering
- One minimal end-to-end processing path

## Drift risks

| Risk | Mitigation |
|------|-----------|
| Source format changes break parsing | Golden bundle tests detect regressions |
| Section structure changes unexpectedly | Invariant checks and section-count drift checks |
| Reference snapshot changes alter outputs unexpectedly | Record snapshot set refs in `ProcessingManifest` |
| Pipeline runs but publishes stale or partial data | Emit `document.processed` only after canonical-ready manifest state |
