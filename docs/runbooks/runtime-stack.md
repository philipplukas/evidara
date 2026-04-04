# Runtime Stack — Architecture & Operations Runbook

Owner: Platform Team
Last reviewed: 2026-04-04
Last verified: 2026-04-04
Applies to: dev, prod

## Purpose

This runbook documents the runtime stack architecture, deployment flow, and
operational procedures for the Evidara Cloud Run services and supporting
infrastructure.

## Architecture Overview

```
┌─────────────────────────────────────────────────────────────────────┐
│                        GitHub Actions                               │
│                                                                     │
│  runtime-images.yml          platform-control-cd.yml                │
│  (build → GHCR + AR)        (deploy → Cloud Run + smoke test)       │
│                                                                     │
│  terraform.yml                                                      │
│  (plan on PR → apply on merge)                                      │
└──────────────┬──────────────────────────────┬───────────────────────┘
               │                              │
               ▼                              ▼
┌──────────────────────┐    ┌─────────────────────────────────────────┐
│  Artifact Registry   │    │           Cloud Run Services            │
│  (europe-west6)      │    │                                         │
│                      │    │  platform-control-api-{env}             │
│  platform-control    │    │  platform-control-worker-{env}          │
│  platform-control-   │    │  legal-search-api-{env}                 │
│    worker            │    │  document-intelligence-consumer-{env}   │
│  legal-search-api    │    │                                         │
│  di-consumer         │    └──────┬──────────────┬───────────────────┘
│                      │           │              │
└──────────────────────┘           │              │
                                   ▼              ▼
                          ┌──────────────┐  ┌───────────┐
                          │   Pub/Sub    │  │ Cloud SQL │
                          │              │  │ PostgreSQL│
                          │  Topics:     │  └───────────┘
                          │  • artifact- │
                          │    bundle-   │
                          │    available │
                          │  • document- │
                          │    processed │
                          │              │
                          │  DLQ topics  │
                          │  per sub     │
                          └──────┬───────┘
                                 │
                                 ▼
                          ┌──────────────┐
                          │     GCS      │
                          │              │
                          │  raw-        │
                          │  artifacts   │
                          │  manifests   │
                          └──────────────┘
```

## Services

| Service | Image | Port | Health | Role |
|---------|-------|------|--------|------|
| platform-control-api | `platform-control` | 8080 | `/health`, `/ready` | REST API, connector management |
| platform-control-worker | `platform-control-worker` | 8080 | `/health` | Pub/Sub pull consumer, connector execution |
| legal-search-api | `legal-search-api` | 3000 | `/health` | NestJS search API, OpenSearch proxy |
| document-intelligence-consumer | `di-consumer` | 8080 | `/health` | Pub/Sub pull consumer, document processing pipeline |

## Infrastructure (Terraform)

### Directory Layout

```
infra/
├── env/
│   ├── dev/
│   │   └── runtime.gcp.tfvars          # Dev environment values
│   └── github.repo_settings.tfvars.example  # GitHub Actions vars
├── terraform/
│   ├── gcp/runtime_stack/              # Main GCP infrastructure
│   │   ├── main.tf                     # Resources (CR, Pub/Sub, GCS, SQL)
│   │   ├── variables.tf                # Input variables
│   │   ├── versions.tf                 # Provider config
│   │   └── outputs.tf                  # Outputs
│   └── github/repo_settings/           # GitHub Actions configuration
│       ├── main.tf                     # Environments, vars, secrets
│       └── variables.tf
```

### Key Resources

| Resource | Type | Purpose |
|----------|------|---------|
| `google_cloud_run_v2_service.runtime` | Cloud Run | All 4 runtime services (dynamic block) |
| `google_pubsub_topic.events` | Pub/Sub | Event mesh topics |
| `google_pubsub_subscription.events` | Pub/Sub | Pull subscriptions with DLQ |
| `google_storage_bucket.raw_artifacts` | GCS | Raw crawl artifact storage |
| `google_storage_bucket.manifests` | GCS | Bundle manifest storage |
| `google_sql_database_instance.platform_control` | Cloud SQL | PostgreSQL for platform-control |
| `google_service_account.runtime` | IAM | Shared runtime SA |

### Applying Changes

```bash
# Plan (from repo root)
cd infra/terraform/gcp/runtime_stack
terraform init
terraform plan -var-file="../../../../infra/env/dev/runtime.gcp.tfvars"

# Apply
terraform apply -var-file="../../../../infra/env/dev/runtime.gcp.tfvars"
```

> **Note**: Terraform plan/apply is automated via CI (`.github/workflows/terraform.yml`).
> PRs touching `infra/terraform/gcp/runtime_stack/**` or `infra/env/dev/runtime.gcp.tfvars`
> will receive an automatic plan comment. Merging to `main` triggers auto-apply.

### GitHub Actions Variables

Managed via `infra/terraform/github/repo_settings/`:

```bash
cd infra/terraform/github/repo_settings
terraform plan -var-file="../../../env/github.repo_settings.tfvars.example"
terraform apply -var-file="../../../env/github.repo_settings.tfvars.example"
```

## CI/CD Pipeline

### Image Build (runtime-images.yml)

**Trigger**: Push to `main` affecting service source code.

1. Builds Docker image per service (parallel jobs)
2. Pushes to **GHCR** (ghcr.io) and **Artifact Registry** (europe-west6-docker.pkg.dev)
3. Tags: `sha-<short>`, `<full-sha>`, `<branch>`, `latest` (main only)
4. PR builds are build-only (no push)

### Service Deploy (platform-control-cd.yml)

**Trigger**: Push to `main` affecting service source or infra config.

1. **Dev**: Deploy all 4 services → smoke test health endpoints
2. **Prod**: Deploy same image SHA that passed dev → smoke test
3. Uses `GCP_ARTIFACT_PROJECT_ID` for image registry (shared across envs)

### Infrastructure (terraform.yml)

**Trigger**: Push to `main` affecting `infra/terraform/gcp/runtime_stack/**`.

- **PR**: `fmt -check` → `validate` → `plan` (posted as PR comment)
- **Main**: `terraform apply -auto-approve`

## Prerequisites

- [ ] `gcloud` CLI authenticated (`gcloud auth login`)
- [ ] Terraform ≥ 1.5 installed
- [ ] Access to GCP project (`data-platform-dev-492214`)
- [ ] GitHub CLI (`gh`) for Actions variable management

## Operational Procedures

### 1. Deploy a Single Service Manually

```bash
export PROJECT_ID="data-platform-dev-492214"
export REGION="europe-west6"
export REPO="runtime"
export SERVICE="platform-control"
export TAG="sha-abc1234"

gcloud run services update "${SERVICE}-dev" \
  --project "${PROJECT_ID}" \
  --region "${REGION}" \
  --image "${REGION}-docker.pkg.dev/${PROJECT_ID}/${REPO}/${SERVICE}:${TAG}"
```

**Expected output**: `Service [platform-control-dev] revision [...] is active`

### 2. Check Service Health

```bash
URL=$(gcloud run services describe "${SERVICE}-dev" \
  --project "${PROJECT_ID}" \
  --region "${REGION}" \
  --format='value(status.url)')

curl -s "${URL}/health" | jq .
```

### 3. View Recent Logs

```bash
gcloud logging read \
  "resource.type=cloud_run_revision AND resource.labels.service_name=${SERVICE}-dev" \
  --project "${PROJECT_ID}" \
  --limit 50 \
  --format json | jq '.[].textPayload'
```

### 4. Check Pub/Sub Dead Letter Queue

```bash
# List DLQ subscriptions
gcloud pubsub subscriptions list \
  --project "${PROJECT_ID}" \
  --filter="name:dlq" \
  --format="table(name,topic)"

# Pull a message from DLQ (for inspection)
gcloud pubsub subscriptions pull "SUBSCRIPTION-dlq-dev" \
  --project "${PROJECT_ID}" \
  --auto-ack --limit 1
```

### 5. Force Redeploy (Same Image)

```bash
gcloud run services update "${SERVICE}-dev" \
  --project "${PROJECT_ID}" \
  --region "${REGION}" \
  --no-traffic  # Deploys new revision without routing traffic

# Then shift traffic
gcloud run services update-traffic "${SERVICE}-dev" \
  --project "${PROJECT_ID}" \
  --region "${REGION}" \
  --to-latest
```

## Rollback

### Rollback to Previous Revision

```bash
# List recent revisions
gcloud run revisions list \
  --service "${SERVICE}-dev" \
  --project "${PROJECT_ID}" \
  --region "${REGION}" \
  --limit 5

# Route traffic to previous revision
gcloud run services update-traffic "${SERVICE}-dev" \
  --project "${PROJECT_ID}" \
  --region "${REGION}" \
  --to-revisions "REVISION_NAME=100"
```

### Rollback Terraform

```bash
# Revert the commit and re-apply
git revert HEAD
git push origin main
# CI will auto-apply the reverted state
```

## Troubleshooting

| Symptom | Likely Cause | Fix |
|---------|-------------|-----|
| Service returns 503 | Container failing health check | Check logs: `gcloud logging read ...`, verify `/health` endpoint |
| DI consumer not processing | Pub/Sub subscription backlog | Check subscription: `gcloud pubsub subscriptions describe ...` |
| DLQ messages accumulating | Permanent processing failures | Pull DLQ message, inspect payload, fix root cause |
| Terraform plan drift | Manual changes outside Terraform | Run `terraform plan` to see drift, then `terraform apply` |
| Image not found on deploy | Image not pushed to Artifact Registry | Check `runtime-images.yml` workflow run, verify AR tag exists |
| Health check timeout | Service startup too slow | Increase `startup_probe.initial_delay_seconds` in tfvars |

## Related

- [ADR-0014: Document Intelligence Pipeline Integration](../adr/0014-document-intelligence-pipeline-integration.md)
- [GitHub Repo Settings README](../../infra/terraform/github/repo_settings/README.md)
- [Runtime GCP tfvars](../../infra/env/dev/runtime.gcp.tfvars)
