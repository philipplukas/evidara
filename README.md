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

## Licensing & Commercial Use

Evidara is **open core**, licensed by artifact type (see
[ADR-0028](docs/adr/adr-0028-open-core-licensing.md)):

| What | License | File |
|---|---|---|
| Platform **code** (`platform-control/`, `document-intelligence/`, `legal-search/`, `infra/`, `scripts/`, `tools/`, `service-template/`, `k8s/`) | **GNU AGPL-3.0-only** | [`LICENSE`](LICENSE) |
| **Data, schemas, contracts** (`contracts/`, `country-overlays/`, `docs/`) | **CC-BY-4.0** | [`LICENSE-data`](LICENSE-data) |

- **Free use.** You may use, study, modify, self-host, and redistribute Evidara
  under these terms at no cost. The AGPL-3.0 requires that if you run a modified
  version as a network service, you offer your modifications under the AGPL-3.0.
- **Commercial use without copyleft.** If you want to use the core in a closed or
  hosted product without the AGPL-3.0's copyleft obligations, a separate
  commercial license may be available — contact the maintainer.
- **Contributing.** External contributions require a signed
  [Contributor License Agreement](CLA.md), which keeps the dual-license option
  open. See [CONTRIBUTING.md](CONTRIBUTING.md).
- **Legal texts.** CC-BY-4.0 covers Evidara's own structuring work (schemas, IDs,
  overlays), not the underlying primary legal sources, which carry their own
  upstream terms. See ADR-0028 §5.

> The copyright holder retains all rights; the licenses above are grants
> extended to others and do not limit the holder's own commercial use.

## Milestones

| Milestone | Description |
|-----------|-------------|
| M0 | Repo Bootstrap |
| M1 | Minimal Platform Control |
| M2 | Minimal Document Intelligence |
| M3 | Minimal Legal Search |
| M4 | First Vertical Slice |
| M5 | Research Workflow Foundation |
