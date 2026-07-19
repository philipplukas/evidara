# Runtime Stack — Architecture & Operations Runbook

Owner: Platform Team
Last reviewed: 2026-04-12
Last verified: 2026-04-12
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
│  legal-search-api    │    │  document-intelligence-document-         │
│  di-consumer         │    │    service-{env}                         │
│  document-           │    │                                         │
│    intelligence-     │    └──────┬──────────────┬───────────────────┘
│    document-service  │           │              │
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
| document-intelligence-document-service | `document-intelligence-document-service` | 8080 | `/health` | Read-only Document Service for full, lean, and text reads backed by published document surfaces |

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
| `google_cloud_run_v2_service.runtime` | Cloud Run | Runtime services from tfvars (e.g. platform-control-api, legal-search-api, di-consumer, document-intelligence-document-service) |
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
- **CI plans:** `infra/env/dev/runtime.gcp.ci.tfvars` and `infra/env/staging/runtime.gcp.ci.tfvars` set `document_intelligence_published_bucket_name = null` and `artifact_bundle_subscription_push = null` so plans against the CI GCP project do not assume environment buckets or push endpoints.

### Document Service

- **Service name:** `document-intelligence-document-service-{env}` via the `cloud_run_services` map in runtime tfvars.
- **Surface source:** the service reads published document rows from `DI_SURFACES_ROOT_URI`, which resolves the `published_documents` Delta surface under the configured root.
- **BFF wiring:** `legal-search-api` must set `DOCUMENT_INTELLIGENCE_BASE_URL` to the matching environment service URL.
- **Auth model:** the current runtime path uses an application bearer secret, not Cloud Run IAM ID tokens. The service validates `DOCUMENT_SERVICE_BEARER_TOKEN`; the BFF sends the same value via `DOCUMENT_INTELLIGENCE_API_KEY`.
- **Operational implication:** when detail reads fall back or return empty bodies, verify the published surface URI and the BFF base URL / bearer pair before replaying source events.

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
> PRs touching `infra/terraform/gcp/runtime_stack/**` or the checked-in runtime tfvars examples
> will receive automatic plan comments for **dev** and **staging**. CI uses `infra/env/*/runtime.gcp.ci.tfvars`
> as an overlay for plan-safe project/service-account overrides. Merging to `main` can trigger applies when enabled:
>
> - `TERRAFORM_APPLY_ENABLED` → dev apply
> - `TERRAFORM_APPLY_ENABLED_STAGING` → staging apply (after dev succeeds)
> - `TERRAFORM_APPLY_ENABLED_PROD` → prod apply (after dev succeeds, and after staging succeeds or is skipped)

### GitHub Actions Variables

Managed via `infra/terraform/github/repo_settings/`:

```bash
cd infra/terraform/github/repo_settings
terraform plan -var-file="../../../env/github.repo_settings.tfvars.example"
terraform apply -var-file="../../../env/github.repo_settings.tfvars.example"
```

## CI/CD Pipeline

### Image Build (runtime-images.yml)

**Trigger**: Push to `main` or PR affecting paths under `.github/workflows/runtime-images.yml`, `platform-control/**`, `legal-search/**`, `document-intelligence/**`, or `contracts/**`.

1. A lightweight **`changes`** job (`dorny/paths-filter`) decides which image jobs run.
2. **Pull requests**: only jobs whose paths changed run (faster CI, fewer self-hosted minutes). Builds do not push (`push: false` on PR).
3. **Push to `main`**: every image job still runs so **all** runtime images exist at the same **`github.sha`** — required because **Runtime Cloud Run CD** deploys every service with that single tag.
4. **`workflow_dispatch`**: all image jobs run (full matrix); use for manual rebuilds.
5. Tags on push / dispatch: `sha-<short>`, `<full-sha>`, `<branch>`, `latest` (main only).

To optimize **main** pushes further (build only what changed), CD would need to deploy **per-service** only when an image tag exists, which breaks the “one SHA for every runtime service” invariant unless you introduce a separate promotion model.

### Service Deploy (platform-control-cd.yml)

**Trigger**: Push to `main` affecting service source or infra config.

1. **Dev**: Deploy all runtime services → smoke test health endpoints
2. **Prod**: Deploy same image SHA that passed dev → smoke test
3. Uses `GCP_ARTIFACT_PROJECT_ID` for image registry (shared across envs)

**Repository variables:** `PLATFORM_CONTROL_SERVICE_NAME` must be the **Cloud Run service name prefix** before `-dev` / `-prod` (for example `platform-control-api`), not the Artifact Registry image repository name (`platform-control`). The image in AR stays `…/platform-control:${IMAGE_TAG}`. See [`infra/env/github.repo_settings.tfvars.example`](../../infra/env/github.repo_settings.tfvars.example).

**IAM:** the Workload Identity Federation service accounts (`GCP_SERVICE_ACCOUNT_DEV` / `GCP_SERVICE_ACCOUNT_PROD` environment secrets) must be allowed to **update** the target Cloud Run services (for example `roles/run.admin` or a custom role including `run.services.update`) in the **runtime** project (`GCP_PROJECT_ID_DEV` / `GCP_PROJECT_ID_PROD`). If deploy fails with `Permission 'run.services.update' denied`, fix IAM on the runtime project, not the artifact project alone.

**Staging:** this workflow has **no** staging deploy job. Use the manual Cloud Run procedure below (or Terraform) for `*-staging` services.

**Prod gate:** in `platform-control-cd.yml`, `deploy-prod` has `needs: deploy-dev`. Add a **manual approval** rule on the GitHub `prod` environment if you want a human promotion step.

**Manual image rebuild:** `runtime-images.yml` also supports `workflow_dispatch` on `main` when you need a full parallel build without a matching push.

**Post-merge verification (Artifact Registry + CD):**

1. For the same commit on `main`, confirm **`Runtime Images`** finished successfully before or in parallel with **`Runtime Cloud Run CD`** (CD polls Artifact Registry for the deployed runtime images: `platform-control`, `platform-control-worker`, `legal-search-api`, `di-consumer`, and `document-intelligence-document-service` at tag `${github.sha}`).
2. Example checks: `gh run list --workflow=runtime-images.yml --branch main --limit 3` and `gh run list --workflow=platform-control-cd.yml --branch main --limit 3`; open the paired runs for the merge commit.
3. **Tfvars / examples:** runtime service images belong under the **`runtime/`** repository in Artifact Registry (see [`infra/env/dev/runtime.gcp.tfvars.example`](../../infra/env/dev/runtime.gcp.tfvars.example) and [`infra/env/staging/runtime.gcp.tfvars.example`](../../infra/env/staging/runtime.gcp.tfvars.example)). Replace any legacy `cloud-run-source-deploy/…` image URLs when updating real tfvars.
4. If CD fails **after** the wait step with **startup probe** errors on `document-intelligence-consumer-*`, the container is exiting or not passing `/health` on `PORT` — this is **not** fixed by retagging alone. Inspect the failing revision logs in Cloud Logging; common causes include invalid `DI_*` env (see `RuntimeSettings` in `document-intelligence`) or IAM for Pub/Sub / GCS. The image built by `runtime-images.yml` uses [`document-intelligence/Dockerfile`](../../document-intelligence/Dockerfile) (`document_intelligence_runtime_ingress` — the push-based FastAPI consumer).

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

**Batch helper:** `scripts/build-runtime-images.sh` runs parallel Cloud Build jobs (see `scripts/cloudbuild.runtime-image.yaml`) for `platform-control`, `platform-control-worker`, `legal-search-api`, `di-consumer`, and `document-intelligence-document-service` with the same tagging defaults.

**DI HTTP ingress only:** the main `document-intelligence/Dockerfile` (used by `runtime-images.yml` for `di-consumer`) now runs the push-based `document_intelligence_runtime_ingress`. `document-intelligence/Dockerfile.runtime-ingress` is equivalent but uses a different build context (for standalone `gcloud builds submit` from the `document-intelligence/` directory; see `cloudbuild.runtime-ingress.yaml`).

### Infrastructure (terraform.yml)

**Trigger**: Push to `main` affecting `infra/terraform/gcp/runtime_stack/**` or checked-in runtime tfvars examples under `infra/env/{dev,staging,prod}/`.

- **PR**: `fmt-check` → separate `plan-dev` + `plan-staging` jobs (`validate` + `plan`, posted as **two** PR comments)
- **Main**: `apply-dev` → optional `apply-staging` → optional `apply-prod` (`terraform apply -auto-approve` in each job)

**Tfvars layering (important):**

- **Examples** (`infra/env/*/runtime.gcp.tfvars.example`) describe the intended runtime wiring for each environment.
- **CI overlays** (`infra/env/*/runtime.gcp.ci.tfvars`) intentionally null out a few expensive / environment-specific edges (notably DI published surfaces + push subscriptions) so PR plans can run safely against the CI GCP project.
- `*.tfvars` files are ignored by default in `.gitignore`; the CI overlay files are tracked via `git add -f` (same pattern as `infra/env/dev/runtime.gcp.ci.tfvars`).

**Repo variables (promotion gates on `main`):**

- `TERRAFORM_APPLY_ENABLED` → runs `apply-dev`
- `TERRAFORM_APPLY_ENABLED_STAGING` → runs `apply-staging` after dev succeeds
- `TERRAFORM_APPLY_ENABLED_PROD` → runs `apply-prod` after dev succeeds and staging is **success or skipped**

**Traceability:** each apply job writes a small table to the GitHub Actions job summary including the commit SHA, tfvars paths, and (for dev) the resolved staging gate flag.

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
2. Executes `os-alias-check-{env}`

There is no `os-alias-bootstrap-{env}` job any more (#713). It created the documents
index with settings and **no mappings**, so every field fell back to dynamic mapping —
facets aggregated to nothing and the German `legal_text` analyzer was absent entirely.
Because it ran before the API and index creation is first-writer-wins, it permanently
pre-empted the API's own correct bootstrap.

The documents index and both aliases are now created by **one** path: the
`legal-search-api` startup bootstrap (`bootstrapDocumentsIndex()`), which derives from
the canonical mapping. This is the same mechanism the live Hetzner runtime uses.

If the alias preflight fails, remediation is to get the API to bootstrap — **not** to
hand-create the index:

```bash
# Ensure the API is allowed to bootstrap (must not be "false"), then roll it.
gcloud run services describe legal-search-api-staging \
  --project "${GCP_PROJECT_ID}" --region "${GCP_REGION}" \
  --format='value(spec.template.spec.containers[0].env)' | grep -o 'OPENSEARCH_BOOTSTRAP_ON_STARTUP[^,]*' || true

gcloud run services update legal-search-api-staging \
  --project "${GCP_PROJECT_ID}" --region "${GCP_REGION}" \
  --update-env-vars=BOOTSTRAP_NUDGE="$(date +%s)"   # forces a new revision

gcloud run jobs execute os-alias-check-staging \
  --project "${GCP_PROJECT_ID}" \
  --region "${GCP_REGION}" \
  --wait
```

Then confirm the result matches canonical:

```bash
cd legal-search/api
OPENSEARCH_NODE=... OPENSEARCH_INDEX=evidara-documents-read-staging \
  npm run mapping:check-drift   # exit 0 is the acceptance criterion
```

### 7. Release Readiness Go/No-Go Operation

`Release Readiness` is the release-lane gate for the GitHub Actions **environment** chosen by repository variable **`RELEASE_READINESS_GITHUB_ENVIRONMENT`** (default **`staging`**). Dev-first orgs should pair **GitHub Environment `dev`** with **`RELEASE_READINESS_E2E_SMOKE_WORKFLOW=E2E Smoke Dev`**; that environment supplies WIF secrets, while **`GCP_PROJECT_ID`**, **`DI_SURFACES_ROOT_URI`**, and **`INTERACTION_FLOW_EVIDENCE_GCS_ROOT`** follow **`dev`** vs **`staging`** repo variables as in [`.github/workflows/release-readiness.yml`](../../.github/workflows/release-readiness.yml). It evaluates six gating signals together:

1. Latest **E2E smoke** result — workflow name defaults to `E2E Smoke Staging`; set **`RELEASE_READINESS_E2E_SMOKE_WORKFLOW`** to `E2E Smoke Dev` when you run the dev smoke train (see [Environment strategy](../setup/environment-strategy.md#operator-posture-dev-first-no-staging-gcp-project)).
2. Latest **`Interaction Flow Staging Evidence`** result (workflow name is still staging-oriented; dev-first orgs may keep this cadence or accept a NO-GO on this row until a dev interaction-flow exists)
3. Interaction-flow artifact completeness quick-check (`scripts/check-latest-interaction-flow-evidence.sh --mode staging`)
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

**Repository variables (optional):**

| Variable | Purpose |
| -------- | ------- |
| `RELEASE_READINESS_GITHUB_ENVIRONMENT` | GitHub **Environment** name for the job (`staging` default). Set to **`dev`** so OIDC uses the **`dev`** environment secrets and GCP project/DI vars resolve to `*_DEV` (same idea as [E2E Smoke Dev](../../.github/workflows/e2e-smoke-dev.yml)). |
| `RELEASE_READINESS_E2E_SMOKE_WORKFLOW` | Exact Actions workflow **display name** for the smoke gate (`E2E Smoke Staging` default). Dev-first: **`E2E Smoke Dev`**. |
| `RELEASE_READINESS_DLQ_SUBSCRIPTION_REGEX` | Monitoring filter regex for DLQ subscription IDs (defaults: **`.*-dev-dlq-sub`** when GitHub env is `dev`, else **`.*-staging-dlq-sub`**). |

#### Environment rotation check

Before switching Release Readiness between `staging` and `dev`:

1. Confirm the live GitHub environments still exist: `gh api repos/philipplukas/evidara/environments --jq '.environments[].name'` should include `dev` and `staging`.
2. Confirm the workflow names still match the docs: `gh api repos/philipplukas/evidara/actions/workflows --jq '.workflows[].name'` should include `E2E Smoke Dev` and `E2E Smoke Staging`.
3. Update the repo vars together so the pair stays aligned: `RELEASE_READINESS_GITHUB_ENVIRONMENT` and `RELEASE_READINESS_E2E_SMOKE_WORKFLOW`.
4. Re-run `gh workflow run "Release Readiness" -f strict=false` and confirm the generated report names the intended environment and smoke workflow before you rotate back or mark the gate authoritative.

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
| E2E smoke gate failed (workflow from `RELEASE_READINESS_E2E_SMOKE_WORKFLOW`, default `E2E Smoke Staging`) | Platform Team | Document-Intelligence Team | Inspect latest smoke logs/artifacts, confirm repo variable matches the smoke you run, rerun after fix |
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
| OpenSearch alias preflight fails in smoke | Missing or broken read/write aliases | Roll `legal-search-api-<env>` so its startup bootstrap re-creates index + aliases from the canonical mapping, then `os-alias-check-<env>`. Never hand-create the index (#713). |
| Facets return empty buckets / umlaut variants do not match | Index created by something other than the canonical bootstrap | `npm run mapping:check-drift` against the cluster; if drifted, reindex via `scripts/opensearch-alias-cutover.ts --stage-write` → backfill → `--promote-read`. Do not weaken the query. |

## Related

- [ADR-0014: Document Intelligence Pipeline Integration](../adr/0014-document-intelligence-pipeline-integration.md)
- [GitHub Repo Settings README](../../infra/terraform/github/repo_settings/README.md)
- Runtime GCP tfvars: `infra/env/dev/runtime.gcp.tfvars` (gitignored — copy from `infra/env/dev/runtime.gcp.tfvars.example`)
