# ADR-0014: Document Intelligence Pipeline Integration

## Status

Accepted

## Date

2026-04-02

## Context

A standalone prototype (`document_intelligence_playground`) validated several pipeline design patterns for legal document ingestion, processing, and serving. The prototype covers:

- **Source adapters** for Swiss (Fedlex SPARQL), German (Gesetze-im-Internet), and Austrian (RIS) legal sources
- A **Policy Resolver** — a YAML-driven rules engine that resolves processing configuration per document type
- A **Medallion architecture** (Bronze/Silver/Gold) with dbt transformations on Databricks
- **Document identity** with stable `document_id` + content-hash `document_version_id`
- **OpenSearch index design** with custom legal text analyzers and chunk-level vector indices

This ADR records which patterns are adopted, where they live, and four design decisions that arose during integration analysis.

## Decisions

### 1. Connector metadata transport

Connector-extracted source hints (jurisdiction, document class, authority) are carried in the existing `source_defaults` and `bundle_metadata` fields on `ArtifactBundleManifest`. These are **hints**, not canonical truth. Platform-control preserves source-time context without being the authority for canonical legal interpretation.

The `ArtifactBundleManifest` already supports this:

- `source_defaults.jurisdiction_id` — default jurisdiction
- `source_defaults.authority_id` — default authority
- `source_defaults.document_type_hint` — document type hint
- `bundle_metadata` — open metadata map for source-specific facts (SR number, ELI URI, etc.)

No schema changes are required.

### 2. Policy Resolver ownership and language

The Policy Resolver lives in `document-intelligence/` and is implemented in Python. Policy selection is consumed directly by DI pipeline stages (parsing, identity resolution, NLP model selection, serving policy). YAML-based policy definitions allow adding new jurisdictions or document types without code changes.

### 3. Connector runtime language

Production connectors are implemented in Python within platform-control, consistent with ADR-0009 which assigns platform-control to Python/FastAPI. The playground's Python adapters can be adopted with minimal modification rather than being ported to a different language.

### 4. Document identity ownership

- **Platform-control** preserves source-native identifiers (`snapshot_external_id`, `source_defaults`) but does NOT assign canonical IDs.
- **Document-intelligence** is the sole authority for canonical `document_id`, `document_version_id`, and `document_revision` assignment.

Identity strategy (from playground's `int_document_identity`):

- `document_id` — stable across re-crawls, derived from `source_document_id` when available, falling back to content-hash lineage
- `document_version_id` — changes when content hash changes
- `document_revision` — monotonic counter per `document_id`

This enables deduplication, version tracking, and skipping re-processing when content hasn't changed.

## Pattern Adoption

| Playground pattern | Adopted? | Target component | Priority |
|---|---|---|---|
| Source adapter ABC + Fedlex adapter | Yes | platform-control | Now |
| Adapter registry | Yes | platform-control | Now |
| Policy Resolver (YAML rules engine) | Yes | document-intelligence | Now |
| Document identity model | Yes | document-intelligence | Next |
| Custom `legal_text_analyzer` | Yes | legal-search | Next |
| `"dynamic": "strict"` on indices | Yes | legal-search | Next |
| Chunk index with `knn_vector` | Deferred | legal-search | Later |
| Medallion architecture with dbt | Not yet | document-intelligence | Later |
| spaCy NLP pipeline | Not yet | document-intelligence | Later |

## Consequences

- Platform-control connectors, document-intelligence pipelines, and OpenSearch indexing jobs share a single language (Python), reducing cross-team friction and enabling model reuse.
- The Policy Resolver introduces a new YAML configuration surface that must be validated in CI.
- Adding a new legal jurisdiction requires: one new connector (PC), one new policy set (DI YAML), and optionally vocabulary updates (contracts). No code changes to legal-search.
- The `ArtifactBundleManifest` schema does not change, since `source_defaults` and `bundle_metadata` already support the required metadata transport.

## References

- [ADR-0002: Top-Level Component Boundaries](0002-top-level-component-boundaries.md)
- [ADR-0009: Technology Stack and Language Boundaries](0009-technology-stack-and-language-boundaries.md)
- [ADR-0012: Layered Contract Governance](0012-layered-contract-governance.md)
- [First Vertical Slice](../components/first-vertical-slice.md)
