# Evidara

**Trustworthy primary law as an API** — a platform that turns messy official legal sources into structured, provenanced, **citable** data: canonical text + provenance + in-force status + a citation graph.

> **Status:** Internal beta — ~12 Swiss federal laws, German UI, CH-first. The strategy is deliberately explicit about what is *built* vs. what is a *bet*: see the [business-model canvas](docs/product/business-model-canvas.md) and [value-proposition canvas](docs/product/value-proposition-canvas.md).

## Why this is hard (the interesting part)

Legal data is **heterogeneous** (every authority publishes differently, down to municipal PDFs), must be **continuously fresh** (stale law is worthless), and has to be **trustworthy enough to cite** — which is an architecture problem, not a scraping one. Evidara is built around that last constraint: a strict separation of *canonical truth* from *serving projections*, provenance on every document, and operator-approved ingestion.

## Fastest way to judge the engineering

Five minutes, in order of signal:

1. **[ADR-0029 — retiring a cloud runtime](docs/adr/0029-self-hosted-hetzner-runtime.md)** — a cost/architecture trade-off made under real constraints (audit → decision → owned trade-offs). Narrative version: [scaling *down* a solo platform](docs/writeups/scaling-down-a-solo-platform.md).
2. **[Boundary contracts](docs/architecture/boundary-contracts.md)** — canonical truth vs. serving projection; search is a rebuildable view, not the system of record.
3. **[Business-model canvas](docs/product/business-model-canvas.md)** — judgment under commercial ambiguity, with every claim tagged built vs. bet.

Prefer to watch? A [5-minute demo script](docs/writeups/demo-script.md) walks the trust loop end to end.

## What is Evidara?

Evidara is a monorepo containing all components of a platform that processes, structures, and serves legal and regulatory documents — designed around strict component boundaries, explicit contracts, and a separation of canonical truth from serving projections.

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
| [`vendor/`](vendor/) | Vendored external pins (for example MacConfig platform contract) |
| [`service-template/`](service-template/) | Conventions for future product (app) Kubernetes / GitOps manifests |
| [`k8s/gitops/`](k8s/gitops/) | Product Kustomize roots for Argo CD (for example `prod/`) |

## MacConfig platform contract

Evidara vendors a pinned copy of the MacConfig cluster platform contract from
`clusters/prod/platform-contract.yaml` in the [MacConfig](https://github.com/philipplukas/MacConfig)
repository (`vendor/platform-contract.yaml` here). To refresh: in a MacConfig checkout run
`make platform-contract-path` (prints the absolute path), copy that file here, then set the pin
below to the same value as `contractVersion` in the YAML; CI enforces they stay in sync.
Operator playbooks: [`docs/migration/`](docs/migration/README.md).

**Pinned MacConfig platform contract:** `0.1.0`

## Main Interaction Flow

```text
platform-control → document-intelligence → legal-search
```

- **platform-control** manages sources, versions, runs, and approvals. It triggers document processing.
- **document-intelligence** receives immutable artifact bundles and produces canonical structured truth in Delta tables.
- **legal-search** consumes canonical truth, projects it into OpenSearch, and serves the user-facing search experience.

Boundaries and contracts between these components are documented in [docs/architecture/boundary-contracts.md](docs/architecture/boundary-contracts.md).

## Key Documentation

- [System Context](docs/architecture/system-context.md) — high-level architecture overview
- [Repository Structure](docs/architecture/repository-structure.md) — what each folder owns and does not own
- [Boundary Contracts](docs/architecture/boundary-contracts.md) — handoff boundaries between components
- [Storage Model](docs/architecture/storage-model.md) — storage technology choices and rationale
- [Implementation Principles](docs/architecture/implementation-principles.md) — guiding design principles
- [Technology Stack And Implementation Plan](docs/architecture/technology-stack-and-implementation-plan.md) — recommended languages, runtimes, tools, and phased delivery choices
- [Communication Model](docs/architecture/communication-model.md) — sync, async, and event-driven patterns
- [ADRs](docs/adr/) — architecture decision records

## Getting Started

See [docs/setup/](docs/setup/) for infrastructure and environment documentation.
For a reproducible shell with Terraform, `gcloud`, `jq`, `shellcheck`, and `uv`, use [Nix dev shell](docs/setup/nix.md) (`nix develop` from the repo root).
Treat Docker as part of the workstation baseline (for example via MacConfig), not as a repo-managed dependency.
For the default live local search ↔ control-panel loop, use `npm run dev:cross-surface:live` from the repo root.
For local end-to-end runtime bring-up, use [Local Vertical Slice Setup](docs/setup/local-vertical-slice.md).
For Zed-specific editor and MCP setup, use [Zed Setup](docs/setup/zed.md).

See each component's doc in [docs/components/](docs/components/) for component-specific guidance.

## Status & what's next

Evidara is at **internal beta**: the full vertical slice — source onboarding → canonical processing → search — runs over a small curated corpus (~12 Swiss federal laws, German UI, CH-first). The original M1–M6 bootstrap roadmap is complete; current direction and open bets are tracked in the [business-model canvas](docs/product/business-model-canvas.md) and [value-proposition canvas](docs/product/value-proposition-canvas.md).

Active work: retiring the usage-billed GCP runtime for a fixed-cost self-hosted stack ([ADR-0029](docs/adr/0029-self-hosted-hetzner-runtime.md)).
