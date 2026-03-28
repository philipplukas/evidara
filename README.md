# Evidara

A clean-room document intelligence platform for legal and regulatory content.

> **Status:** Architecture and bootstrap phase — structure, boundaries, documentation, and governance are in place. Implementation will follow the phased plan outlined in [docs/components/first-vertical-slice.md](docs/components/first-vertical-slice.md).

## What is Evidara?

Evidara is a monorepo containing all components of a document intelligence platform that processes, structures, and serves legal and regulatory documents. It is designed around strict component boundaries, explicit contracts, and a separation of canonical truth from serving projections.

**This is a clean-room implementation.** See [docs/architecture/clean-room-principles.md](docs/architecture/clean-room-principles.md).

## Repository Structure

| Folder | Purpose |
|--------|---------|
| [`platform-control/`](platform-control/) | Source lifecycle, reference data, run orchestration, approvals, and internal ops workflows |
| [`document-intelligence/`](document-intelligence/) | Raw-to-canonical processing: parsing, segmentation, citation extraction, and Delta truth |
| [`legal-search/`](legal-search/) | Frontend, BFF, OpenSearch serving projections, search and document APIs |
| [`contracts/`](contracts/) | OpenAPI specs, JSON Schemas, event schemas, shared IDs, and evidence refs |
| [`infra/`](infra/) | Terraform, deployment definitions, environment setup, cloud resource provisioning |
| [`docs/`](docs/) | Architecture, ADRs, onboarding, runbooks, implementation principles, component plans |
| [`scripts/`](scripts/) | Shared utility scripts |

## Main Interaction Flow

```
platform-control → document-intelligence → legal-search
```

- **platform-control** manages sources, versions, runs, and approvals. It triggers document processing.
- **document-intelligence** receives raw artifacts and produces canonical structured truth in Delta tables.
- **legal-search** consumes canonical truth, projects it into OpenSearch, and serves the user-facing search experience.

Boundaries and contracts between these components are documented in [docs/architecture/boundary-contracts.md](docs/architecture/boundary-contracts.md).

## Key Documentation

- [System Context](docs/architecture/system-context.md) — high-level architecture overview
- [Repository Structure](docs/architecture/repository-structure.md) — what each folder owns and does not own
- [Boundary Contracts](docs/architecture/boundary-contracts.md) — handoff boundaries between components
- [Storage Model](docs/architecture/storage-model.md) — storage technology choices and rationale
- [Implementation Principles](docs/architecture/implementation-principles.md) — guiding design principles
- [Communication Model](docs/architecture/communication-model.md) — sync, async, and event-driven patterns
- [ADRs](docs/adr/) — architecture decision records

## Getting Started

See [docs/setup/](docs/setup/) for infrastructure and environment documentation.

See each component's doc in [docs/components/](docs/components/) for component-specific guidance.

## Milestones

| Milestone | Description |
|-----------|-------------|
| M0 | Repo Bootstrap |
| M1 | Minimal Platform Control |
| M2 | Minimal Document Intelligence |
| M3 | Minimal Legal Search |
| M4 | First Vertical Slice |
| M5 | Research Workflow Foundation |
