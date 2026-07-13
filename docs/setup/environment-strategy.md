# Environment Strategy

## Overview

The **canonical** Evidara model is three environments: **dev**, **staging**, and **prod**, each provisioned from the same Terraform modules with environment-specific variable files under `[../../infra/env/](../../infra/env/)`.

### Operator posture: dev-first (no staging GCP project)

Some teams (especially small ones) run only **dev** and **prod** in GCP and use **dev** as the shared integration surface. That is a valid posture:

- Operator evidence that other runbooks label “staging” (for example **TAR-85** / MVP acceptance JSON) should be collected against **dev Cloud Run** URLs and the same `evidara workflow mvp-acceptance` command.
- **Re-evaluate** whether to add a dedicated staging project when you need prod-like isolation, stable demo URLs, or release gates that must not depend on dev churn (see [Phase 5 go / no-go memo](../runbooks/phase-5-go-no-go-memo.md) and your Linear **TAR-69** thread).
- **Release Readiness** (`.github/workflows/release-readiness.yml`) can run in GitHub **Environment `dev`** so WIF + GCP APIs target your dev project: set repository variable **`RELEASE_READINESS_GITHUB_ENVIRONMENT`** to `dev` (default remains `staging`). Pair with **`RELEASE_READINESS_E2E_SMOKE_WORKFLOW`** = `E2E Smoke Dev` and ensure the GitHub `dev` environment defines the same OIDC secrets as [E2E Smoke Dev](../../.github/workflows/e2e-smoke-dev.yml) (`GCP_WORKLOAD_IDENTITY_PROVIDER`, `GCP_SERVICE_ACCOUNT_DEV`) plus repo variables **`GCP_PROJECT_ID_DEV`**, **`DI_SURFACES_ROOT_URI_DEV`**, and optional **`INTERACTION_FLOW_EVIDENCE_GCS_ROOT_DEV`**. DLQ monitoring defaults to subscription IDs matching **`.*-dev-dlq-sub`** in dev; override with **`RELEASE_READINESS_DLQ_SUBSCRIPTION_REGEX`** if your Terraform naming differs. Interaction-flow gates still use the **Interaction Flow Staging Evidence** workflow and `--mode staging` artifact checks until a dev-native flow exists.

`infra/env/staging/` and staging-oriented GitHub workflows remain in the repo for organizations that **do** operate staging; they are not removed when a team is dev-first.

For quick **HTTP checks** against platform-control and legal-search (after pointing env vars at dev/staging URLs), use `[tools/evidara-cli](../../tools/evidara-cli/README.md)` or `EVIDARA_CLI_SMOKE=1 bash scripts/smoke-evidara-cli.sh` (see [CONTRIBUTING.md](../../CONTRIBUTING.md)).

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
- Same OpenSearch index mappings

Differences between environments are limited to:

- Resource sizing (CPU, memory, replicas)
- Database instance tier
- Storage bucket names (suffixed with environment)
- Secret values (different per environment, never in Git)

## Configuration Management

| Concern            | Mechanism                                                 |
| ------------------ | --------------------------------------------------------- |
| Infrastructure     | Terraform with per-env `tfvars`                           |
| Application config | Environment variables injected at deploy time             |
| Secrets            | Google Secret Manager, referenced by name                 |
| Feature flags      | Environment variables (simple) or config service (future) |

## Evidara CLI env vars (dev / staging / prod)

Use `[tools/evidara-cli](../../tools/evidara-cli/README.md)` for quick HTTP checks against **platform-control** and **legal-search** in any environment. Set the variables below from **deploy-time config**, **Google Secret Manager**, or your **operator runbook** — never commit real URLs that embed credentials, API keys, or bearer tokens.

| Variable                           | Default (local)         | Purpose                                                                                                             |
| ---------------------------------- | ----------------------- | ------------------------------------------------------------------------------------------------------------------- |
| `EVIDARA_PLATFORM_CONTROL_URL`     | `http://localhost:8000` | Platform-control base URL                                                                                           |
| `EVIDARA_PLATFORM_CONTROL_TOKEN`   | *(empty)*               | `Authorization: Bearer …` for private Cloud Run (IAM invoker); mint per service URL audience                        |
| `EVIDARA_PLATFORM_CONTROL_API_KEY` | *(empty)*               | `X-API-Key` when the API requires it                                                                                |
| `EVIDARA_LEGAL_SEARCH_URL`         | `http://localhost:3102` | Legal-search BFF base URL                                                                                           |
| `EVIDARA_LEGAL_SEARCH_TOKEN`       | *(empty)*               | `Authorization: Bearer …` when configured                                                                           |
| `EVIDARA_LEGAL_SEARCH_API_KEY`     | *(empty)*               | `X-API-Key` when the API requires it                                                                                |
| `EVIDARA_CLI_HUMAN`                | `0`                     | Set to `1` for indented JSON (`evidara` output)                                                                     |
| `EVIDARA_REPO_ROOT`                | *(auto)*                | Optional override for `evidara openapi paths`                                                                       |
| `EVIDARA_CLI_SMOKE`                | *(unset)*               | Set to `1` with `[scripts/smoke-evidara-cli.sh](../../scripts/smoke-evidara-cli.sh)` to run both `ping` subcommands |

For **shell** checks against private Cloud Run (`scripts/e2e-smoke-test.sh`, `scripts/mvp-acceptance-scenario-pack.sh`), set `**EVIDARA_GCP_IMPERSONATE_SERVICE_ACCOUNT`** to a service account that has `roles/run.invoker` on the target services; your user needs `roles/iam.serviceAccountTokenCreator` on that SA. This matches `[.github/workflows/e2e-smoke-dev.yml](../../.github/workflows/e2e-smoke-dev.yml)` (and `e2e-smoke-staging.yml` when staging exists). Optional helpers: `[scripts/mint-cloud-run-tokens.sh](../../scripts/mint-cloud-run-tokens.sh)`, `[scripts/evidara-cloud-run-operator-session.sh](../../scripts/evidara-cloud-run-operator-session.sh)`. Step-by-step IAM: [GCP local Cloud Run auth](gcp-local-cloud-run-auth.md).

After exporting the URLs and optional auth vars for the target environment:

```bash
EVIDARA_CLI_SMOKE=1 bash scripts/smoke-evidara-cli.sh
```

For a **manual run from GitHub Actions**, use workflow `[.github/workflows/evidara-cli-remote-smoke.yml](../../.github/workflows/evidara-cli-remote-smoke.yml)`: choose GitHub **environment** `dev` or `staging`, pass both API base URLs; the workflow mints Cloud Run ID tokens via OIDC (no static Bearer secrets). Optional repository secrets: `EVIDARA_PLATFORM_CONTROL_API_KEY`, `EVIDARA_LEGAL_SEARCH_API_KEY`. Step-by-step: [Evidara CLI remote smoke — operator](../runbooks/evidara-cli-remote-smoke-operator.md). Per-environment command checklist: [CLI environment smoke matrix](../runbooks/evidara-cli-environment-smoke-matrix.md). Terraform: `[infra/terraform/github/repo_settings](../../infra/terraform/github/repo_settings/README.md)`.

## Folder Structure

```text
infra/
  terraform/
    gcp/          # GCP resources (modules)
    opensearch/   # Self-managed OpenSearch on GKE (modules)
    github/       # GitHub repo settings (modules)
  env/
    dev/          # dev.tfvars, dev-specific overrides
    staging/      # staging.tfvars, staging-specific overrides
    prod/         # prod.tfvars, prod-specific overrides
```

Current example files:

- `[../../infra/env/dev/runtime.gcp.tfvars.example](../../infra/env/dev/runtime.gcp.tfvars.example)`
- `[../../infra/env/staging/runtime.gcp.tfvars.example](../../infra/env/staging/runtime.gcp.tfvars.example)`
- `[../../infra/env/prod/runtime.gcp.tfvars.example](../../infra/env/prod/runtime.gcp.tfvars.example)`
- `[../../infra/env/dev/opensearch.gke.tfvars.example](../../infra/env/dev/opensearch.gke.tfvars.example)`
- `[../../infra/env/staging/opensearch.gke.tfvars.example](../../infra/env/staging/opensearch.gke.tfvars.example)`
- `[../../infra/env/prod/opensearch.gke.tfvars.example](../../infra/env/prod/opensearch.gke.tfvars.example)`

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
