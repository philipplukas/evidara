# Runtime Stack — Architecture & Operations Runbook

Owner: Platform Team
Last reviewed: 2026-04-09
Last verified: 2026-04-06
Applies to: dev, staging, prod

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
│    worker            │    │  di-consumer-{env} (HTTP DI ingress)    │
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
| di-consumer | `di-consumer` (image `runtime/di-consumer`) | 8080 | `/health` | HTTP ingress: Pub/Sub **push** to `/internal/events/artifact-bundles:process`, Delta publish + outbound status/processed topics |

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
| `google_cloud_run_v2_service.runtime` | Cloud Run | Runtime services from tfvars (e.g. platform-control-api, legal-search-api, di-consumer) |
| `google_pubsub_topic.events` | Pub/Sub | Event mesh topics |
| `google_pubsub_subscription.events` | Pub/Sub | Pull subscriptions with DLQ |
| `google_storage_bucket.raw_artifacts` | GCS | Raw crawl artifact storage |
| `google_storage_bucket.manifests` | GCS | Bundle manifest storage |
| `google_sql_database_instance.platform_control` | Cloud SQL | PostgreSQL for platform-control |
| `google_service_account.runtime` | IAM | Per-service runtime SAs (map in tfvars) |
| `google_storage_bucket_iam_member.document_intelligence_*` | GCS IAM | `document_intelligence` SA: read raw artifacts bucket; optional admin on published-surfaces bucket |

### Document intelligence (`di-consumer`)

- **Service account:** Use `service_account_key = "document_intelligence"` in `cloud_run_services` so the service runs as the Terraform-managed DI SA (not the default compute SA). That SA receives project-level Pub/Sub publish/subscribe and storage roles from `runtime_stack`; bucket-level bindings add explicit read on **raw artifacts** and optional **objectAdmin** on the **published Delta surfaces** bucket.
- **Published surfaces bucket:** Set `document_intelligence_published_bucket_name` in tfvars (e.g. `evidara-document-intelligence-surfaces-dev`). The bucket must already exist; Terraform only attaches IAM.
- **Pub/Sub push:** Set `artifact_bundle_subscription_push` with the subscription map key for `artifact-bundle-available` in that environment and `target_service = "di-consumer"`. That merges `push_config` onto the existing pull-style subscription definition without duplicating the whole `event_subscriptions` block.
- **CI plans:** `infra/env/dev/runtime.gcp.ci.tfvars` sets `document_intelligence_published_bucket_name = null` and `artifact_bundle_subscription_push = null` so plans against the CI GCP project do not assume dev buckets or push endpoints.

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
> PRs touching `infra/terraform/gcp/runtime_stack/**` or `infra/env/dev/runtime.gcp.tfvars.example`
> will receive an automatic plan comment. CI uses `infra/env/dev/runtime.gcp.ci.tfvars`
> as an overlay for plan-safe project/service-account overrides. Merging to `main`
> triggers auto-apply.

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

### Manual image build (Cloud Build)

Use this when you need an image in Artifact Registry **without** waiting for `runtime-images.yml` (for example, hotfix validation on dev). Prefer the **same Dockerfile and context** as CI so the image matches what Actions would produce.

**Tag:** use the **full git commit SHA** (`git rev-parse HEAD`) as the image tag. That matches `platform-control-cd.yml`, which deploys with `IMAGE_TAG: ${{ github.sha }}`. CI also publishes `sha-<short>` aliases; a manual build typically only pushes the tag you pass.

**Project:** pass `--project` to `gcloud builds submit` for the GCP project that **hosts Artifact Registry** (often the same as the runtime project; see `infra/env/*/runtime.gcp.tfvars` and `cloud_run_services` image hostnames).

**Platform:** Cloud Run expects **linux/amd64**. The checked-in Cloud Build configs pass `--platform linux/amd64`. For local `docker build` on Apple Silicon, add `--platform linux/amd64` before push.

**gcloud Python:** if `gcloud builds submit` fails because `CLOUDSDK_PYTHON` points at a missing interpreter (for example an old repo venv path), use a system Python:

```bash
export CLOUDSDK_PYTHON=/usr/bin/python3
```

**Single service (examples from repo root):**

```bash
TAG="$(git rev-parse HEAD)"
export CLOUDSDK_PYTHON=/usr/bin/python3

gcloud builds submit . \
  --project "${ARTIFACT_PROJECT_ID}" \
  --config=platform-control/cloudbuild.api.yaml \
  --substitutions=_TAG="${TAG}"

gcloud builds submit . \
  --project "${ARTIFACT_PROJECT_ID}" \
  --config=platform-control/cloudbuild.worker.yaml \
  --substitutions=_TAG="${TAG}"
```

**Batch helper:** `scripts/build-runtime-images.sh` runs parallel Cloud Build jobs (see `scripts/cloudbuild.runtime-image.yaml`) for `platform-control`, `platform-control-worker`, `legal-search-api`, and `di-consumer` with the same tagging defaults.

**DI HTTP ingress only:** the image wired for Pub/Sub push to the ingress service is built from `document-intelligence/Dockerfile.runtime-ingress` — use `document-intelligence/cloudbuild.runtime-ingress.yaml` for that variant (not the default `document-intelligence/Dockerfile` used by `runtime-images.yml` for `di-consumer`).

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

Cloud Run service **names** include the role suffix (for example `platform-control-api-dev`), while Artifact Registry **images** use shorter names (for example `runtime/platform-control`). Use the runtime GCP project for `--project` on `gcloud run` (not necessarily the same as the registry project if you split them).

```bash
export RUNTIME_PROJECT_ID="evidara-dev"
export ARTIFACT_PROJECT_ID="evidara-dev"   # registry host project; often same as runtime
export REGION="europe-west6"
export REPO="runtime"
export TAG="$(git rev-parse HEAD)"   # or any tag you pushed (e.g. sha-abc1234 from CI)

gcloud run services update "platform-control-api-dev" \
  --project "${RUNTIME_PROJECT_ID}" \
  --region "${REGION}" \
  --image "${REGION}-docker.pkg.dev/${ARTIFACT_PROJECT_ID}/${REPO}/platform-control:${TAG}"
```

**Expected output**: a new ready revision for `platform-control-api-dev`.

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

### 6. Bootstrap Runtime Schema & OpenSearch Aliases

Use this after fresh environment bring-up (or when smoke preflight reports missing aliases):

```bash
export GCP_PROJECT_ID="data-platform-dev-492214"
export GCP_REGION="europe-west6"
bash scripts/run-runtime-bootstrap.sh staging
```

What it does:

1. Executes `platform-control-db-migrate-{env}`
2. Executes `os-alias-bootstrap-{env}`
3. Executes `os-alias-check-{env}`

If staging smoke fails with:

`OpenSearch alias preflight failed. Run job os-alias-bootstrap-staging and retry smoke.`

remediation is:

```bash
gcloud run jobs execute os-alias-bootstrap-staging \
  --project "${GCP_PROJECT_ID}" \
  --region "${GCP_REGION}" \
  --wait

gcloud run jobs execute os-alias-check-staging \
  --project "${GCP_PROJECT_ID}" \
  --region "${GCP_REGION}" \
  --wait
```

### 7. Release Readiness Go/No-Go Operation

`Release Readiness` is the release-lane gate of truth for `staging`. It
evaluates six gating signals together:

1. Latest `E2E Smoke Staging` result
2. Latest `Interaction Flow Staging Evidence` result
3. Interaction-flow artifact completeness quick-check
4. Latest `Terraform` workflow result
5. DI schema drift preflight
6. DLQ depth (15-minute max undelivered messages)

The generated report also includes:

- an `Evidence quality score` row derived from the interaction-flow run plus artifact completeness
- a copy/paste `Runbook Verification Log Row` when the interaction-flow artifact quick-check passes
- a GCS copy of the rendered report at `${INTERACTION_FLOW_EVIDENCE_GCS_ROOT}/release-readiness/<run_id>/report.md`

Manual trigger options:

```bash
# Strict blocking mode (default)
gh workflow run "Release Readiness" -f strict=true

# Investigation mode (non-blocking run, still reports GO/NO-GO)
gh workflow run "Release Readiness" -f strict=false
```

#### Required status check on `main`

To enforce Release Readiness as a merge gate (see Linear P6-1 / branch protection policy):

1. GitHub → **Settings** → **Rules** (rulesets) or **Branches** → protection for `main`.
2. Enable **Require status checks to pass before merging**.
3. Add the check for workflow [`.github/workflows/release-readiness.yml`](../../.github/workflows/release-readiness.yml): job id `release-readiness`. On pull requests the required check name is usually **`Release Readiness / release-readiness`** — confirm against the checks list on an open PR after the workflow has run at least once.
4. Save and verify a draft PR cannot merge when that check is failing or pending.

**Evidence:** capture a screenshot or ruleset export showing the required check, and link a green `Release Readiness` workflow run used for validation.

**Linear P6-1 ([TAR-77](https://linear.app/tart-baozi/issue/TAR-77)):** attach the screenshot/export plus the workflow run URL as issue evidence so merges are auditable.

**Stability:** renaming the workflow `name:` or the job id breaks branch protection until the rule is updated.

Interpretation:

- `GO`: all six gating signals pass in the generated report.
- `NO-GO`: at least one signal failed; follow owner-first remediation below
  before attempting release.

### 8. NO-GO Owner Matrix (first response)

| Signal | Primary owner | Backup owner | First response |
|--------|---------------|--------------|----------------|
| E2E Smoke Staging failed | Platform Team | Document-Intelligence Team | Inspect latest smoke logs/artifacts, rerun after fix |
| Interaction Flow Staging Evidence failed | Platform Team | Legal-Search Team | Inspect Playwright artifacts, screenshot pack output, and rerun staging evidence |
| Interaction-flow artifact completeness failed | Platform Team | Legal-Search Team | Run `scripts/check-latest-interaction-flow-evidence.sh --mode staging`, repair missing artifact contents, rerun gate |
| Terraform workflow failed/drifted | Platform Team | Repo Maintainer on duty | Resolve plan/apply failure and rerun Terraform workflow |
| DI schema drift preflight failed | Document-Intelligence Team | Platform Team | Investigate surface schema drift, remediate per DI runbook, rerun gate |
| DLQ depth non-zero | Platform Team | Legal-Search Team | Triage DLQ root cause and replay per DLQ runbook |

### 9. Weekly Readiness Review Cadence

- Frequency: once per week (recommended Monday morning UTC).
- Inputs: latest `Release Readiness` artifact + previous week incident notes.
- Output: short checkpoint note with current `GO/NO-GO`, open risks, and
  remediation owners.
- Tracking: attach checkpoint note link to the active release-hardening Linear
  issue.

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
| OpenSearch alias preflight fails in smoke | Missing or broken read/write aliases | Run `scripts/run-runtime-bootstrap.sh <env>` or execute `os-alias-bootstrap-<env>` then `os-alias-check-<env>` |

## Related

- [ADR-0014: Document Intelligence Pipeline Integration](../adr/0014-document-intelligence-pipeline-integration.md)
- [GitHub Repo Settings README](../../infra/terraform/github/repo_settings/README.md)
- Runtime GCP tfvars: `infra/env/dev/runtime.gcp.tfvars` (gitignored — copy from `infra/env/dev/runtime.gcp.tfvars.example`)
