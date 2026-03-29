# Legal Search

## Purpose

Serve legal and document search and detail experiences to users. Legal-search is the user-facing serving layer that consumes published canonical surfaces from document-intelligence and turns them into OpenSearch projections and UI/API responses.

## Current state

The `legal-search/` folder contains the migrated frontend application. The BFF, projection worker, and OpenSearch integration are not yet implemented.

## Source of truth

- Published canonical surfaces from document-intelligence are read-only inputs
- OpenSearch holds serving projections only
- `contracts/api/legal-search.openapi.yaml` defines the user-facing API

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

## Minimal next tasks

- [ ] Define search projection schema
- [ ] Define initial OpenSearch mapping and alias strategy
- [ ] Define projection manifest/history model
- [ ] Implement `document.withdrawn` ingestion and deindex/tombstone behavior, including replay ordering tests
- [ ] Define minimal NestJS BFF endpoints
- [ ] Define reindex workflow

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
| Later | Facets and ranking improvements |
| Later | Semantic search |
| Later | Richer document exploration |

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
