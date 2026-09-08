# Repository Structure
> **Platform commands here have moved.** `deploy-stage{1,2,3,8}.sh`,
> `deploy-observability.sh`, `deploy-runners.sh` and the `values/` files now live in
> [research-platform](https://github.com/philipplukas/research-platform) (`scripts/`, `data/`,
> `identity/`, `observability/`). The copies under `infra/hetzner/` are frozen duplicates
> awaiting deletion — see [`infra/hetzner/OWNERSHIP.md`](../../infra/hetzner/OWNERSHIP.md).
> Stages 4 and 5 are still run from this repository.

## Overview

Evidara uses a monorepo with top-level domain folders. Each folder represents a distinct component with clear ownership boundaries.

## Folder Ownership

### `platform-control/`

**Owns:**

- Jurisdictions, authorities, and reference data management
- Seed sources and source registry
- Source versions and version lifecycle
- Approvals and approval workflows
- Run records and run orchestration
- Internal ops workflows
- Future research workflow control

**Does NOT own:**

- Canonical document entities (owned by document-intelligence)
- Search indexes or serving projections (owned by legal-search)
- User-facing search UI (owned by legal-search)

---

### `document-intelligence/`

**Owns:**

- Raw artifact ingestion and parsing
- Document segmentation
- Jurisdiction assignment to documents
- Citation extraction
- Canonical domain entities: documents, sections, citations, relationships
- Processing jobs and the NATS JetStream consumers (`jobs/nats_consumer.py`, `jobs/projection_bridge_consumer.py`)
- Delta table definitions and canonical truth (written by the pure-Python `deltalake` sink onto MinIO)

**Does NOT own:**

- Source lifecycle or approvals (owned by platform-control)
- Search indexes or serving projections (owned by legal-search)
- Run orchestration (owned by platform-control)

---

### `legal-search/`

**Owns:**

- Next.js frontend
- NestJS BFF (Backend for Frontend)
- OpenSearch index definitions and serving projections
- Search API endpoints
- Document detail API endpoints
- User-facing search, browse, and document exploration

**Does NOT own:**

- Canonical document truth (owned by document-intelligence)
- Source management or approvals (owned by platform-control)
- Document processing or parsing (owned by document-intelligence)

---

### `contracts/`

**Owns:**

- `api/` — OpenAPI specs for synchronous APIs
- `schemas/` — JSON Schemas for shared domain objects
- `events/` — JSON Schemas for async event payloads
- `ids/` — ID naming and formatting conventions

**Does NOT own:**

- Implementation code
- Runtime services
- Storage definitions

---

### `infra/`

**Owns:**

- `hetzner/` — the **live runtime**: staged, idempotent deploy scripts (`deploy-stage1.sh` … `deploy-stage5.sh`), helm values, and app manifests for the self-hosted single-node k3s cluster ([ADR-0029](../adr/0029-self-hosted-hetzner-runtime.md)). Run from a laptop against the cluster — not GitOps, not CI.
- `terraform/gcp/` — legacy Google Cloud infrastructure. Still present, **not destroyed**; the Cloud Run CD workflow is feature-flagged off behind `vars.ENABLE_GCP_CLOUD_RUN_CD`.
- `terraform/github/` — GitHub repository governance automation
- `env/dev | staging | prod/` — Environment-specific configurations

**Does NOT own:**

- Application code
- Business logic
- Domain schemas

---

### `docs/`

**Owns:**

- `architecture/` — System-level architecture documentation
- `adr/` — Architecture Decision Records
- `components/` — Per-component documentation and plans
- `migration/` — MacConfig GitOps migration maps, inventory, Argo cutover checklists
- `runbooks/` — Operational procedures
- `setup/` — Infrastructure and environment setup guides

---

### `service-template/`

**Owns:**

- Placeholder and future conventions for **product** Kubernetes manifests (Argo-synced workloads),
  aligned with `vendor/platform-contract.yaml`.

**Does NOT own:**

- Platform namespaces, cluster RBAC, or admission policies (MacConfig).

---

### `k8s/gitops/`

**Owns:**

- Product-facing Kustomize roots (for example `prod/`) intended to be synced by Argo CD per `docs/migration/`.

**Status:** **scaffolding, not the live deployment path.** These manifests still carry
placeholder hostnames (`*.evidara.example`), `prod/` is empty, and they have never been
applied. The cluster is deployed by `infra/hetzner/deploy-stage*.sh` instead.

**Does NOT own:**

- MacConfig platform namespaces, baseline `NetworkPolicy`, or cluster RBAC.

---

### `scripts/`

**Owns:**

- Shared utility scripts used across components
- Build and development helper scripts

---

### `.github/`

**Owns:**

- Issue templates
- PR templates
- GitHub Actions workflows
- CODEOWNERS
