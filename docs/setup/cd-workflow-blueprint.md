# CD Workflow Blueprint (GitHub Actions + Google Cloud)

## Purpose

This page translates the CD strategy into an implementable GitHub Actions design for a `dev`/`prod` environment model.

Use this as the template for service-specific workflows.

Current implemented example:

- [`../../.github/workflows/platform-control.yml`](../../.github/workflows/platform-control.yml)
- [`../../.github/workflows/document-intelligence.yml`](../../.github/workflows/document-intelligence.yml)
- [`../../.github/workflows/document-intelligence-cd.yml`](../../.github/workflows/document-intelligence-cd.yml)
- [`../../.github/workflows/platform-control-cd.yml`](../../.github/workflows/platform-control-cd.yml)

## Baseline Principles

- Build once per merge commit on `main`
- Publish immutable artifact references (image digest, wheel version, bundle artifact version)
- Auto deploy to `dev`
- Promote the same artifact to `prod` behind GitHub environment approval
- Keep infra workflows separate from app/data service workflows

## GitHub Environments

Create two GitHub environments:

- `dev` (no manual reviewers)
- `prod` (required reviewers + optional deployment wait timer)

Store environment-specific non-secret variables/secrets in each environment.

## Required Repository Secrets and Variables

Typical set for Google Cloud OIDC deployment:

- `GCP_WORKLOAD_IDENTITY_PROVIDER`
- `GCP_SERVICE_ACCOUNT_DEV`
- `GCP_SERVICE_ACCOUNT_PROD`
- `GCP_PROJECT_ID_DEV`
- `GCP_PROJECT_ID_PROD`
- `GCP_ARTIFACT_PROJECT_ID`
- `GCP_REGION`
- `ARTIFACT_REGISTRY_REPOSITORY`
- service-specific values (for example `PLATFORM_CONTROL_SERVICE_NAME`, `LEGAL_SEARCH_API_SERVICE_NAME`, Databricks host/profile references)

For `document-intelligence` specifically, configure per-environment secrets:

- `DATABRICKS_HOST`
- `DATABRICKS_TOKEN`

Repository environments/variables/secrets can be provisioned via Terraform in [`../../infra/terraform/github/repo_settings`](../../infra/terraform/github/repo_settings) with example inputs in [`../../infra/env/github.repo_settings.tfvars.example`](../../infra/env/github.repo_settings.tfvars.example).

For CLI-driven synchronization (discovery via `gcloud`/Databricks CLI and write via `gh`), use [`../../scripts/sync-github-cd-config.sh`](../../scripts/sync-github-cd-config.sh). It supports dry-run by default, optional secret sync via Google Secret Manager, optional Databricks PAT sourcing from local Databricks CLI profiles (`--databricks-token-source profile`) with Secret Manager rotation, auto-detection for common WIF/token naming patterns, and an `--interactive` mode for account/project selection when gcloud context needs fixing.

Recommended first run:

```bash
scripts/sync-github-cd-config.sh \
  --interactive \
  --preflight \
  --sync-secrets
```

Then run with `--apply` after preflight passes.

Recommended token rotation flow (Databricks CLI profile -> Secret Manager -> GitHub):

```bash
scripts/sync-github-cd-config.sh \
  --dev-project data-platform-dev-492214 \
  --prod-project data-platform-prod-492214 \
  --region europe-west6 \
  --artifact-project data-platform-dev-492214 \
  --artifact-repo runtime \
  --platform-control-service platform-control \
  --wif-provider "projects/585502170445/locations/global/workloadIdentityPools/github/providers/evidara" \
  --service-account-dev "gha-deployer-dev@data-platform-dev-492214.iam.gserviceaccount.com" \
  --service-account-prod "gha-deployer-prod@data-platform-prod-492214.iam.gserviceaccount.com" \
  --databricks-profile-dev DEFAULT \
  --databricks-profile-prod DEFAULT \
  --databricks-token-source profile \
  --gsm-token-secret-dev evidara-databricks-token-dev \
  --gsm-token-secret-prod evidara-databricks-token-prod \
  --sync-secrets \
  --apply
```

## Minimum IAM and Access

The operator running the sync script needs:

- GitHub repo admin/write access for Actions variables/secrets/environments
- GCP access to list/describe target projects
- GCP access to list workload identity pools/providers
- GCP access to list service accounts in dev/prod projects
- GCP Secret Manager access to list secrets and read latest token secret versions
- Databricks CLI configured for profile-based host discovery (or explicit host flags)

## Failure Recovery

If sync fails with project/permission errors:

1. Re-run with interactive account/project selection:
   `scripts/sync-github-cd-config.sh --interactive --preflight --sync-secrets`
2. Confirm the active gcloud account can see both target projects.
3. Re-run with explicit overrides for values that cannot be auto-detected.
4. Use `--preflight` until all checks pass, then run with `--apply`.

## Ownership Boundary

- Terraform stack [`../../infra/terraform/github/repo_settings`](../../infra/terraform/github/repo_settings) remains the long-term source of truth.
- The sync script is intended for bootstrap/discovery/operational plumbing.
- After manual/script changes, keep Terraform state aligned (import/apply) to prevent drift.

Prefer GitHub OIDC with Workload Identity Federation instead of static service account keys.

## Common Workflow Shape

```text
on push to main (path-filtered)
  -> build + test + publish artifact
  -> deploy_dev (environment=dev)
  -> verify_dev smoke
  -> deploy_staging (environment=staging, optional gate)
  -> verify_staging smoke
  -> deploy_prod (environment=prod, approval required)
  -> verify_prod smoke
```

## Reusable Skeleton: Cloud Run Service

Use this for `platform-control` and `legal-search` deployables.

```yaml
name: Deploy Platform Service

on:
  push:
    branches: [main]
    paths:
      - "platform-control/**"
      - ".github/workflows/platform-control-cd.yml"

permissions:
  contents: read
  id-token: write

jobs:
  build_and_publish:
    runs-on: ubuntu-latest
    outputs:
      image_digest: ${{ steps.publish.outputs.image_digest }}
    steps:
      - uses: actions/checkout@v4
      - name: Build image
        run: echo "Build container image"
      - name: Publish image
        id: publish
        run: |
          echo "image_digest=us-docker.pkg.dev/project/repo/service@sha256:..." >> "$GITHUB_OUTPUT"

  deploy_dev:
    runs-on: ubuntu-latest
    needs: build_and_publish
    environment: dev
    steps:
      - name: Auth to GCP (OIDC)
        run: echo "Authenticate with dev service account"
      - name: Deploy to Cloud Run dev
        run: |
          echo "gcloud run deploy ... --image '${{ needs.build_and_publish.outputs.image_digest }}'"
      - name: Smoke check dev
        run: echo "Run service health/smoke tests"

  deploy_staging:
    runs-on: ubuntu-latest
    needs: [build_and_publish, deploy_dev]
    environment: staging
    steps:
      - name: Auth to GCP (OIDC)
        run: echo "Authenticate with staging service account"
      - name: Deploy to Cloud Run staging
        run: |
          echo "gcloud run deploy ... --image '${{ needs.build_and_publish.outputs.image_digest }}'"
      - name: Smoke check staging
        run: echo "Run service health/smoke tests"

  deploy_prod:
    runs-on: ubuntu-latest
    needs: [build_and_publish, deploy_staging]
    environment: prod
    steps:
      - name: Auth to GCP (OIDC)
        run: echo "Authenticate with prod service account"
      - name: Deploy to Cloud Run prod
        run: |
          echo "gcloud run deploy ... --image '${{ needs.build_and_publish.outputs.image_digest }}'"
      - name: Smoke check prod
        run: echo "Run service health/smoke tests"
```

## Reusable Skeleton: Document Intelligence (Databricks)

Use this for `document-intelligence` bundle promotion.

```yaml
name: Deploy Document Intelligence

on:
  push:
    branches: [main]
    paths:
      - "document-intelligence/**"
      - ".github/workflows/document-intelligence-cd.yml"

permissions:
  contents: read
  id-token: write

jobs:
  build_bundle_artifact:
    runs-on: ubuntu-latest
    outputs:
      artifact_version: ${{ steps.meta.outputs.artifact_version }}
    steps:
      - uses: actions/checkout@v4
      - name: Build wheel/bundle artifact
        run: echo "Build package for Databricks job"
      - name: Capture artifact version
        id: meta
        run: |
          echo "artifact_version=${GITHUB_SHA}" >> "$GITHUB_OUTPUT"

  deploy_dev:
    runs-on: ubuntu-latest
    needs: build_bundle_artifact
    environment: dev
    steps:
      - name: Authenticate to Databricks
        run: echo "Auth using dev profile/workspace"
      - name: Deploy bundle to dev
        run: echo "databricks bundle deploy --target dev"
      - name: Run lightweight smoke
        run: echo "databricks bundle run document_intelligence_smoke --target dev"

  deploy_staging:
    runs-on: ubuntu-latest
    needs: [build_bundle_artifact, deploy_dev]
    environment: staging
    steps:
      - name: Authenticate to Databricks
        run: echo "Auth using staging profile/workspace"
      - name: Deploy bundle to staging
        run: echo "databricks bundle deploy --target staging"
      - name: Run staging smoke
        run: echo "databricks bundle run document_intelligence_smoke --target staging"

  deploy_prod:
    runs-on: ubuntu-latest
    needs: [build_bundle_artifact, deploy_staging]
    environment: prod
    steps:
      - name: Authenticate to Databricks
        run: echo "Auth using prod profile/workspace"
      - name: Deploy bundle to prod
        run: echo "databricks bundle deploy --target prod"
      - name: Run post-deploy smoke
        run: echo "Run prod smoke and fail fast on contract regressions"
```

## Implemented reference workflows (this repo)

These are concrete implementations of the patterns above (use them as the “real” blueprint when docs and skeleton diverge):

### Databricks bundle CD

- Workflow: [`.github/workflows/document-intelligence-cd.yml`](../../.github/workflows/document-intelligence-cd.yml)
- Bundle targets: [`document-intelligence/databricks.yml`](../../document-intelligence/databricks.yml)
- Promotion: `dev -> staging -> prod` with GitHub Environments (`dev`, `staging`, `prod`)

### GCP `runtime_stack` Terraform

- Workflow: [`.github/workflows/terraform.yml`](../../.github/workflows/terraform.yml)
- Terraform root: [`infra/terraform/gcp/runtime_stack`](../../infra/terraform/gcp/runtime_stack)
- Checked-in tfvars examples: [`infra/env/README.md`](../../infra/env/README.md)
- PR plans: separate plan comments for **dev** and **staging** (each uses a `*.ci.tfvars` overlay to keep CI plans safe)
- `main` applies: `apply-dev` → optional `apply-staging` → optional `apply-prod`, gated by repo variables:
  - `TERRAFORM_APPLY_ENABLED`
  - `TERRAFORM_APPLY_ENABLED_STAGING`
  - `TERRAFORM_APPLY_ENABLED_PROD`

## Infra Workflow Separation

Keep Terraform in dedicated workflows, for example:

- `runtime-infra-plan.yml` on PR
- `runtime-infra-apply.yml` on merge to `main` (or manual dispatch)

Do not couple infra apply to service deployment jobs in the same workflow.

## Path Filter Guidance

Use path filters so each service deploys only when relevant files change.

Recommended include sets:

- `platform-control/**` and its workflow file
- `legal-search/api/**`, `legal-search/frontend/**` and their workflow files
- `document-intelligence/**`, `contracts/**` where contract drift affects runtime behavior

## Smoke Verification Minimum

Each deploy workflow should include a small, deterministic smoke check:

- Cloud Run: `/health` plus one business endpoint assertion
- Document intelligence: minimal job run or validation task against non-production data

Treat smoke as blocking for promotion to `prod`.

## Rollback Pattern

- Cloud Run: redeploy previous known-good digest or shift traffic to previous revision
- Databricks: redeploy previous bundle artifact version and rerun smoke validation

Capture rollback commands in component runbooks as implementation progresses.
