# ADR-0005: Search Strategy

## Status

Accepted

## Date

2026-03-28

## Context

The platform needs to provide fast, user-facing search over legal and regulatory documents. We need to choose a search technology and define its role in the architecture.

## Decision

- Use **OpenSearch** (not Elasticsearch) as the search engine.
- Search is a **serving layer only** — not a source of truth.

## Rationale

### Why OpenSearch over Elasticsearch

- OpenSearch is the open-source fork of Elasticsearch with an Apache 2.0 license.
- No licensing ambiguity or vendor lock-in concerns.
- Feature-compatible with Elasticsearch for our use cases (full-text search, faceting, aggregations).
- Active community and cloud-managed options available.

### Why serving layer only

- Search indexes are **derived from canonical truth** (Delta tables).
- If an OpenSearch index is lost, corrupted, or needs changes, it is rebuilt from canonical source.
- This separation allows:
  - Independent evolution of search projections without affecting canonical data.
  - Reindexing with different mappings, analyzers, or projections.
  - Search outages that do not affect data integrity.

## Consequences

- legal-search must implement a sync/projection mechanism from Delta to OpenSearch.
- Reindex capabilities must be built as a core workflow, not an afterthought.
- No business logic should assume data only exists in OpenSearch.
- OpenSearch schema changes are serving-layer concerns, not truth-layer concerns.
