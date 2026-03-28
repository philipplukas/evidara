# Infrastructure Overview

## Overview

Evidara uses three cloud/platform providers for its infrastructure:

- **Google Cloud Platform (GCP)** — primary cloud provider
- **Databricks** — document intelligence processing
- **GitHub** — source control, CI/CD, governance

## GCP Services

| Service | Purpose | Used by |
|---------|---------|---------|
| **Cloud Run** | Application runtime | platform-control, legal-search BFF |
| **Cloud SQL (Postgres)** | Relational database | platform-control |
| **Cloud Storage (GCS)** | Object storage for raw artifacts | platform-control, document-intelligence |
| **Pub/Sub** | Asynchronous event messaging | All components |
| **Secret Manager** | Credential and secret storage | All components |
| **Cloud DNS** | DNS management | All components |
| **Cloud Monitoring** | Observability | All components |

### Pub/Sub Topics

| Topic | Producer | Consumer |
|-------|----------|----------|
| `raw-artifact-available` | platform-control | document-intelligence |
| `document-processed` | document-intelligence | legal-search |
| `index-update-requested` | ops / document-intelligence | legal-search |

### Cloud Storage Buckets

| Bucket | Purpose |
|--------|---------|
| `evidara-raw-artifacts-{env}` | Raw artifacts from runs |
| `evidara-processed-{env}` | Processing intermediaries (if needed) |

### Cloud SQL

| Instance | Database | Used by |
|----------|----------|---------|
| `evidara-control-{env}` | `platform_control` | platform-control |

## Databricks

| Resource | Purpose |
|----------|---------|
| Workspace | Document intelligence processing |
| Delta tables | Canonical document truth storage |
| Workflows / Jobs | Processing pipeline orchestration |
| Unity Catalog | Data governance (future) |

### Delta Table Paths

| Table | Purpose |
|-------|---------|
| `evidara.canonical.documents` | Canonical document entities |
| `evidara.canonical.sections` | Document sections |
| `evidara.canonical.citations` | Extracted citations (future) |

## OpenSearch

| Cluster | Purpose |
|---------|---------|
| `evidara-search-{env}` | Search serving for legal-search |

Provider TBD: managed OpenSearch (AWS, Aiven, or self-managed).

### Indexes

| Index | Purpose |
|-------|---------|
| `documents` | Document search projections |
| `sections` | Section-level search (future) |

## Deployment Model

| Component | Deployment Target | Notes |
|-----------|-------------------|-------|
| platform-control | Cloud Run | Connects to Cloud SQL, GCS, Pub/Sub |
| document-intelligence | Databricks | Triggered by Pub/Sub → Cloud Function bridge or Databricks webhook |
| legal-search (BFF) | Cloud Run | Connects to OpenSearch |
| legal-search (frontend) | Cloud Run or CDN | Static assets + server components |

## No Secrets in Git

All credentials are stored in **Google Secret Manager** and injected at runtime. See [SECURITY.md](../../SECURITY.md) for details.
