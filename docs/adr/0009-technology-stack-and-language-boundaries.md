# ADR-0009: Technology Stack and Language Boundaries

## Status

Proposed

## Date

2026-03-30

## Context

Evidara is a multi-component legal technology platform that requires different languages and runtimes for different problem domains:

- **User-facing applications** benefit from a unified TypeScript stack (frontend + backend) for fast iteration, shared types, and a single dependency ecosystem.
- **Data acquisition and document intelligence** require Python for its mature NLP/ML ecosystem (spaCy, Docling, Spark), Databricks native support, and libraries for PDF/XML parsing.
- **Data modeling** is best expressed in SQL (dbt, Delta tables).
- **Infrastructure** uses Terraform/HCL as the industry standard.

Without explicit boundaries, the platform risks accumulating unnecessary language sprawl (e.g., Go for a service that could be TypeScript, or TypeScript for a Databricks job).

## Decision

### Language Assignment by Component

| Component | Primary Language | Runtime | Rationale |
|-----------|-----------------|---------|-----------|
| **legal-search frontend** | TypeScript | Next.js (React) | Shared types with BFF, SSR, rich interactivity |
| **legal-search BFF** | TypeScript | NestJS / Node.js | Shared types with frontend, OpenAPI generation |
| **platform-control** | Python | FastAPI / uvicorn | Databricks integration, shared models with DI |
| **document-intelligence** | Python | Databricks (Spark) / local CLI | NLP/ML ecosystem, Docling, Delta Lake |
| **OpenSearch indexing** | Python | Standalone job | Shared models with DI, Docling chunking |
| **Infrastructure** | HCL | Terraform | Industry standard for GCP/Databricks |
| **Contracts** | JSON Schema + OpenAPI | N/A | Language-neutral, machine-validated |

### Prohibited Alternatives (MVP)

The following are explicitly deferred to prevent premature complexity:

- **Go** — not justified when TypeScript (for APIs) and Python (for data) cover all current needs
- **Rust** — no performance-critical hot path exists yet
- **Java/Kotlin** — no JVM services planned; Databricks uses PySpark
- **Ruby** — no Rails-shaped problems

### Shared Code Policy

- **No cross-language shared libraries.** Communication between TypeScript and Python components uses contracts (JSON Schema, OpenAPI, events).
- **Within-language sharing** uses workspace packages (npm/pip).

## Rationale

- Two primary languages (TypeScript + Python) is the minimum viable set that covers frontend, API, NLP, and data processing.
- Language assignment follows data shape: TypeScript where the primary data is HTTP request/response cycles; Python where the primary data is documents, text, and ML models.
- Explicit prohibition of alternatives prevents "let's try Go for this one service" drift.

## Consequences

- All new services must justify deviation from this table.
- The team must maintain competency in both TypeScript and Python.
- Cross-component communication overhead is managed through contracts, not shared code.
- This ADR should be revisited when performance profiling identifies a need for a compiled language.

## References

- [Technology Stack and Implementation Plan](../architecture/technology-stack-and-implementation-plan.md)
- [ADR-0002: Top-Level Component Boundaries](0002-top-level-component-boundaries.md)
- [ADR-0004: Contract Strategy](0004-contract-strategy.md)
