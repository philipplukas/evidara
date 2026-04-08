# Environment Strategy

## Overview

Evidara uses three environments: **dev**, **staging**, and **prod**. All environments are provisioned from the same Terraform modules with environment-specific variable files.

Initial environment scaffolding now exists for the `document-intelligence` Databricks stack under [`../../infra/env/`](../../infra/env/).

For quick **HTTP checks** against platform-control and legal-search (after pointing env vars at dev/staging URLs), use [`tools/evidara-cli`](../../tools/evidara-cli/README.md) or `EVIDARA_CLI_SMOKE=1 bash scripts/smoke-evidara-cli.sh` (see [CONTRIBUTING.md](../../CONTRIBUTING.md)).

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

## Evidara CLI env vars (dev / staging / prod)

Use [`tools/evidara-cli`](../../tools/evidara-cli/README.md) for quick HTTP checks against **platform-control** and **legal-search** in any environment. Set the variables below from **deploy-time config**, **Google Secret Manager**, or your **operator runbook** — never commit real URLs that embed credentials, API keys, or bearer tokens.

| Variable | Default (local) | Purpose |
|----------|-----------------|---------|
| `EVIDARA_PLATFORM_CONTROL_URL` | `http://localhost:8000` | Platform-control base URL |
| `EVIDARA_PLATFORM_CONTROL_API_KEY` | _(empty)_ | `X-API-Key` when the API requires it |
| `EVIDARA_LEGAL_SEARCH_URL` | `http://localhost:3102` | Legal-search BFF base URL |
| `EVIDARA_LEGAL_SEARCH_TOKEN` | _(empty)_ | `Authorization: Bearer …` when configured |
| `EVIDARA_LEGAL_SEARCH_API_KEY` | _(empty)_ | `X-API-Key` when the API requires it |
| `EVIDARA_CLI_HUMAN` | `0` | Set to `1` for indented JSON (`evidara` output) |
| `EVIDARA_REPO_ROOT` | _(auto)_ | Optional override for `evidara openapi paths` |
| `EVIDARA_CLI_SMOKE` | _(unset)_ | Set to `1` with [`scripts/smoke-evidara-cli.sh`](../../scripts/smoke-evidara-cli.sh) to run both `ping` subcommands |

After exporting the URLs and optional auth vars for the target environment:

```bash
EVIDARA_CLI_SMOKE=1 bash scripts/smoke-evidara-cli.sh
```

For a **manual run from GitHub Actions**, use workflow [`.github/workflows/evidara-cli-remote-smoke.yml`](../../.github/workflows/evidara-cli-remote-smoke.yml): pass service base URLs as inputs and configure repository secrets `EVIDARA_PLATFORM_CONTROL_API_KEY`, `EVIDARA_LEGAL_SEARCH_TOKEN`, and `EVIDARA_LEGAL_SEARCH_API_KEY` when those environments require auth.

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
