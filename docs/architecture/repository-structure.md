# Repository Structure

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
- Databricks pipelines
- Delta table definitions and canonical truth

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

- `terraform/gcp/` — Google Cloud infrastructure
- `terraform/databricks/` — Databricks workspace and resources
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
- `runbooks/` — Operational procedures
- `setup/` — Infrastructure and environment setup guides

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
