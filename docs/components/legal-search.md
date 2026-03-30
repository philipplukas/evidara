# Legal Search

## Purpose

Serve legal and document search and detail experiences to users. Legal-search is the user-facing serving layer that consumes canonical truth from document-intelligence and presents it through search, browse, and document exploration interfaces.

## Current state

The `legal-search/` folder contains the Next.js frontend application, migrated from the earlier `omnilex-search` project. See the [legal-search workspace manifest](../../legal-search/package.json) for the workspace entry point. The backend BFF (NestJS) and OpenSearch integration are not yet implemented.

## Source of truth

- Delta tables (read-only) for canonical documents — legal-search never writes to Delta
- OpenSearch for the serving projection index — this is a projection, not the source of truth
- `contracts/api/legal-search.openapi.yaml` for API definition

## Responsibilities

### Minimal v1

- Index canonical document projections into OpenSearch
- Expose search API
- Expose document detail API
- Serve minimal frontend search experience

### Boundary

- **Does own:** frontend (Next.js), BFF (NestJS), OpenSearch index management, search and detail APIs
- **Does NOT own:** canonical document truth, source management, document processing

## Minimal next tasks

- [ ] Define search projection schema (what gets indexed)
- [ ] Define initial OpenSearch index mapping
- [ ] Define minimal NestJS BFF endpoints
- [ ] Define minimal Next.js UI pages (search, document detail)
- [ ] Define reindex workflow
- [ ] Define sync mechanism from canonical entities to search documents

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
| Later | Richer document exploration (relationships, cross-references) |

## Dependencies

| Dependency | Purpose |
|-----------|---------|
| OpenSearch | Search index and query engine |
| Delta tables | Read canonical documents for projection building |
| Pub/Sub | Consume `document.processed` and `index_update.requested` events |
| Cloud Run | Runtime for BFF and frontend |

## Technology

| Concern | Technology |
|---------|-----------|
| Frontend | Next.js |
| BFF | NestJS |
| Search Engine | OpenSearch |
| Runtime | Cloud Run (GCP) |

## Key Contracts

- **Consumes:** `document.processed` event from document-intelligence
- **Consumes:** `index_update.requested` event
- **API:** `contracts/api/legal-search.openapi.yaml`
- **Reads:** canonical truth from Delta (for projection building)

## Testing

See [Legal Search Testing](testing/legal-search-testing.md) for the full testing strategy.

Key tests:

- Projection builder unit tests
- Search and detail API contract tests
- Indexing smoke test with 3–5 sample docs
- 3–5 fixed search smoke queries
- Minimal frontend tests: search page render, detail page render, one user flow
- Indexing parity check: canonical docs vs indexed docs

## Drift risks

| Risk | Mitigation |
|------|-----------|
| Search index diverges from canonical data | Indexing parity checks |
| Projection logic drops fields | Projection builder unit tests |
| Search results empty when docs exist | Search smoke queries after every reindex |
| Detail page missing expected fields | API contract tests |
| Source format changes affect search quality | Golden queries with expected results |
