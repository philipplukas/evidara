# ADR-0002: Top-Level Component Boundaries

## Status

Accepted

## Date

2026-03-28

## Context

The platform needs clear boundaries between its major functional areas to ensure separation of concerns, independent evolution, and explicit contracts.

## Decision

Define six top-level components:

| Component | Responsibility | Primary Technology |
|-----------|---------------|-------------------|
| `platform-control` | Source lifecycle, reference data, runs, approvals, orchestration | Python / FastAPI |
| `document-intelligence` | Raw-to-canonical processing, Delta truth | Python / Databricks |
| `legal-search` | User-facing search, OpenSearch projections, frontend and API | TypeScript / Next.js + NestJS |
| `contracts` | Shared schemas, APIs, events, IDs | YAML / JSON |
| `infra` | Terraform, deployment, environments | HCL |
| `docs` | Architecture, ADRs, runbooks, component plans | Markdown |

## Rationale

- **platform-control** is separated from processing because source management and document processing have different lifecycles, failure modes, and scaling characteristics.
- **document-intelligence** is separated from search serving because canonical truth (Delta) and serving projections (OpenSearch) serve different purposes and should not be coupled.
- **legal-search** is separated from intelligence because the user-facing experience should not be entangled with batch processing pipelines.
- **contracts** are extracted because they are the shared language and should be independently reviewable and versionable.

## Consequences

- All cross-component interactions must go through contracts.
- Each component can be developed, tested, and deployed independently (within contract constraints).
- Component ownership must be documented and enforced via CODEOWNERS.
