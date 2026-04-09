# Infrastructure Overview

## Overview

This page describes the target-state infrastructure plan for Evidara. The repo is still pre-runtime, so these entries should be read as intended deployment architecture unless a component explicitly says otherwise.

Evidara targets three cloud/platform providers:

- **Google Cloud Platform (GCP)** — target primary cloud provider for runtime services
- **Databricks** — target document-intelligence processing and published canonical surfaces
- **GitHub** — current source control and CI/CD system

## Local Runtime Stack

For vertical-slice local development, use the repo compose stack plus helper script:

- `bash scripts/local-vertical-slice.sh up` to start Postgres, OpenSearch, and Pub/Sub emulator
- `bash scripts/local-vertical-slice.sh env` to print local env wiring
- guide: [Local Vertical Slice Setup](./local-vertical-slice.md)

## GCP Services

| Service | Purpose | Used by |
|---------|---------|---------|
| **Cloud Run** | Application runtime | platform-control, legal-search BFF |
| **Cloud SQL (Postgres)** | Relational database | platform-control |
| **Cloud Storage (GCS)** | Raw artifacts and manifests | platform-control, document-intelligence |
| **Pub/Sub** | Asynchronous event messaging | All components |
| **Secret Manager** | Credential and secret storage | All components |
| **Google Kubernetes Engine (GKE)** | Self-managed OpenSearch runtime | legal-search |
| **Cloud DNS** | DNS management | All components |
| **Cloud Monitoring** | Observability | All components |

### Pub/Sub Topics

| Topic | Producer | Consumer |
|-------|----------|----------|
| `artifact-bundle-available` | platform-control | document-intelligence |
| `document-processing-status-updated` | document-intelligence | platform-control |
| `document-processed` | document-intelligence | legal-search |
| `document-withdrawn` | document-intelligence | legal-search |
| `index-update-requested` | ops / legal-search | legal-search |

> Topic names use kebab-case infrastructure identifiers. Internal `event_type` values use dotted snake_case. Example: topic `artifact-bundle-available` maps to event type `artifact_bundle.available`.
>
> Event payloads should continue to use the shared CloudEvents-aligned envelope defined in `contracts/common/event-envelope.schema.json`.

### Cloud Storage Buckets

| Bucket | Purpose |
|--------|---------|
| `evidara-raw-artifacts-{env}` | Raw artifacts from connector runs |
| `evidara-manifests-{env}` | Bundle manifests and related immutable manifest objects |

Manifests should be stored as immutable JSON objects. Search and filtering over manifest metadata should come from mirrored query surfaces, not from Hive-style path semantics.

### Cloud SQL

| Instance | Database | Used by |
|----------|----------|---------|
| `evidara-control-{env}` | `platform_control` | platform-control |

### Secret and env management

Evidara uses a split model for runtime configuration:

- **Terraform-managed**: secret containers (names), IAM access, and Cloud Run secret references.
- **Ops/CI-managed**: secret values (Secret Manager versions), injected after Terraform and rotated independently.

Secret categories:

- **Upstream-provided** (must match provider values): Firecrawl API key/webhook secret, OpenSearch endpoint and credentials.
- **Internally generated** (platform-owned): service bearer tokens, internal webhook shared secrets, generated DB credentials where applicable.

Standard deployment flow:

1. `terraform apply` infrastructure and secret containers. If `terraform` is missing locally, use the [Nix dev shell](nix.md) (`nix develop`).
2. Add/update secret values in Secret Manager.
   - For self-managed OpenSearch on GKE, sync stack outputs with `scripts/sync_opensearch_secrets.py`.
3. Deploy or roll Cloud Run services to load latest secret versions.
4. Verify health and event flow.

## Databricks

| Resource | Purpose |
|----------|---------|
| Workspace | Document intelligence processing |
| Delta tables | Canonical truth and processing manifests |
| Published views or tables | Stable downstream surfaces for legal-search |
| Unity Catalog lineage | Table, job, and published-surface lineage inside DI |
| Workflows / Jobs | Processing pipeline orchestration |

Current repo scaffolding splits ownership this way:

- Terraform under [`../../infra/terraform/databricks/document_intelligence_stack`](../../infra/terraform/databricks/document_intelligence_stack) wires the top-level Databricks workspace/environment layer and invokes the reusable module under [`../../infra/terraform/databricks/document_intelligence`](../../infra/terraform/databricks/document_intelligence)
- Terraform under [`../../infra/terraform/gcp/runtime_stack`](../../infra/terraform/gcp/runtime_stack) provisions environment runtime primitives (GCS, Pub/Sub, service accounts, Secret Manager placeholders, Cloud SQL and Cloud Run scaffolding)
- Terraform under [`../../infra/terraform/opensearch/gke_stack`](../../infra/terraform/opensearch/gke_stack) provisions self-managed OpenSearch on GKE with dedicated networking
- Environment tfvars under [`../../infra/env/`](../../infra/env/) provide `dev` / `staging` / `prod` planning inputs for runtime GCP, GKE OpenSearch, and DI Databricks stacks
- Databricks Asset Bundle files under [`../../document-intelligence/`](../../document-intelligence/) define the DI processing job
- SQL/bootstrap assets under [`../../document-intelligence/databricks/sql`](../../document-intelligence/databricks/sql) register the published Delta surfaces after the first successful write
- GitHub Actions validates the DI Terraform path plus the Databricks bundle/runtime shape before merge

### Published Surfaces

| Surface | Purpose |
|---------|---------|
| `published_documents` | Canonical document revisions |
| `published_sections` | Canonical sections |
| `processing_manifests` | Exact immutable DI processing results |

## OpenSearch

| Cluster | Purpose |
|---------|---------|
| `evidara-search-{env}` | Search serving for legal-search |

Search is provisioned through the dedicated GKE stack (`infra/terraform/opensearch/gke_stack`) and exposed privately in a dedicated VPC. Runtime services consume endpoint and credentials from Secret Manager after syncing stack outputs. It remains a serving layer only and must be rebuildable from published DI surfaces. Alias cutover and replay scripting currently live in `legal-search/api/scripts/opensearch-alias-cutover.ts`.

Recommended lifecycle pattern:

- versioned physical indices
- stable read/write aliases
- bulk replay for rebuilds
- projection manifest/history inside `legal-search`

## Optional Later Additions

| Capability | When to add it |
|-----------|----------------|
| OpenLineage | If DI, control-plane, and search lineage need one cross-platform model |
| External metadata/catalog tool | If contract discovery and lineage UX outgrow docs + code review |

## Deployment Model

| Component | Deployment Target | Notes |
|-----------|-------------------|-------|
| platform-control | Cloud Run | Connects to Cloud SQL, GCS, Pub/Sub |
| document-intelligence | Databricks | Triggered by Pub/Sub and reads bundle manifests + artifacts |
| legal-search (BFF) | Cloud Run | Connects to OpenSearch |
| legal-search (frontend) | Cloud Run or CDN | Static assets + server components |
