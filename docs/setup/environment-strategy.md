# Environment Strategy

## Overview

Evidara uses three environments: **dev**, **staging**, and **prod**. All environments are provisioned from the same Terraform modules with environment-specific variable files.

Initial environment scaffolding now exists for the `document-intelligence` Databricks stack under [`../../infra/env/`](../../infra/env/).

## Environments

### dev

- **Purpose:** Active development and experimentation
- **Data:** Synthetic or sampled data only
- **Access:** Development team
- **Stability:** May be unstable; frequent deployments
- **Cost:** Minimal resource sizing

### staging

- **Purpose:** Pre-production validation and integration testing
- **Data:** Representative subset of production data (anonymized if needed)
- **Access:** Development and QA teams
- **Stability:** Should be stable; deploys before prod
- **Cost:** Close to production sizing for realistic testing

### prod

- **Purpose:** Production serving
- **Data:** Real production data
- **Access:** Restricted to production operators
- **Stability:** High availability; changes require review
- **Cost:** Full production sizing with autoscaling

## Environment Parity

All environments use:

- Same Terraform modules (different `tfvars`)
- Same container images (different tags/versions)
- Same Databricks job definitions (different clusters/sizing)
- Same OpenSearch index mappings

Differences between environments are limited to:

- Resource sizing (CPU, memory, replicas)
- Database instance tier
- Storage bucket names (suffixed with environment)
- Secret values (different per environment, never in Git)

## Configuration Management

| Concern | Mechanism |
|---------|-----------|
| Infrastructure | Terraform with per-env `tfvars` |
| Application config | Environment variables injected at deploy time |
| Secrets | Google Secret Manager, referenced by name |
| Feature flags | Environment variables (simple) or config service (future) |

## Folder Structure

```text
infra/
  terraform/
    gcp/          # GCP resources (modules)
    databricks/   # Databricks resources (modules)
    github/       # GitHub repo settings (modules)
  env/
    dev/          # dev.tfvars, dev-specific overrides
    staging/      # staging.tfvars, staging-specific overrides
    prod/         # prod.tfvars, prod-specific overrides
```

Current example files:

- [`../../infra/env/dev/document_intelligence.databricks.tfvars`](../../infra/env/dev/document_intelligence.databricks.tfvars)
- [`../../infra/env/staging/document_intelligence.databricks.tfvars`](../../infra/env/staging/document_intelligence.databricks.tfvars)
- [`../../infra/env/prod/document_intelligence.databricks.tfvars`](../../infra/env/prod/document_intelligence.databricks.tfvars)
- [`../../infra/env/dev/runtime.gcp.tfvars.example`](../../infra/env/dev/runtime.gcp.tfvars.example)
- [`../../infra/env/staging/runtime.gcp.tfvars.example`](../../infra/env/staging/runtime.gcp.tfvars.example)
- [`../../infra/env/prod/runtime.gcp.tfvars.example`](../../infra/env/prod/runtime.gcp.tfvars.example)
- [`../../infra/env/dev/opensearch.gke.tfvars.example`](../../infra/env/dev/opensearch.gke.tfvars.example)
- [`../../infra/env/staging/opensearch.gke.tfvars.example`](../../infra/env/staging/opensearch.gke.tfvars.example)
- [`../../infra/env/prod/opensearch.gke.tfvars.example`](../../infra/env/prod/opensearch.gke.tfvars.example)

Runtime stack module checks can be run locally with:

- `bash scripts/check-runtime-stack.sh`

## Naming Conventions

Resources follow this pattern:

```text
evidara-{component}-{resource}-{env}
```

Examples:

- `evidara-control-db-dev` — dev Postgres instance
- `evidara-raw-artifacts-staging` — staging GCS bucket
- `evidara-search-prod` — production OpenSearch cluster

## Deployment Flow

```text
dev → staging → prod
```

1. Changes deploy to **dev** first (automatic on merge to main, or manual).
2. After validation, promote to **staging** (manual trigger or scheduled).
3. After staging validation, promote to **prod** (manual trigger with approval).
