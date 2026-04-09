# GitHub Repo Settings Terraform Stack

Manages GitHub repository delivery configuration for Evidara:

- Repository environments (`dev`, `prod`, optional `staging`)
- Repository Actions variables
- Environment Actions variables
- Repository Actions secrets
- Environment Actions secrets

## Usage

Run from this directory:

```bash
terraform init
terraform plan -var-file="../../../env/github.repo_settings.tfvars.example"
```

To apply with real secret values, provide sensitive maps via environment variables instead of committing them:

```bash
export TF_VAR_environment_secrets='{
  "dev": {
    "GCP_WORKLOAD_IDENTITY_PROVIDER": "projects/123/locations/global/workloadIdentityPools/github/providers/evidara",
    "GCP_SERVICE_ACCOUNT_DEV": "gha-deployer-dev@evidara-dev.iam.gserviceaccount.com",
    "DATABRICKS_HOST": "https://dbc-xxxx.cloud.databricks.com",
    "DATABRICKS_TOKEN": "..."
  },
  "staging": {
    "GCP_WORKLOAD_IDENTITY_PROVIDER": "projects/123/locations/global/workloadIdentityPools/github/providers/evidara",
    "GCP_SERVICE_ACCOUNT_STAGING": "gha-deployer-staging@project-dacd6b7b-dc96-4534-b82.iam.gserviceaccount.com",
    "E2E_SMOKE_STAGING_SLACK_WEBHOOK": "https://hooks.slack.com/services/..."
  },
  "prod": {
    "GCP_WORKLOAD_IDENTITY_PROVIDER": "projects/123/locations/global/workloadIdentityPools/github/providers/evidara",
    "GCP_SERVICE_ACCOUNT_PROD": "gha-deployer-prod@evidara-prod.iam.gserviceaccount.com",
    "DATABRICKS_HOST": "https://dbc-yyyy.cloud.databricks.com",
    "DATABRICKS_TOKEN": "..."
  }
}'

terraform apply -var-file="../../../env/github.repo_settings.tfvars.example"
```

### Repository-level secrets (`TF_VAR_repository_secrets`)

Use for **long-lived** values only (API keys, static third-party tokens). Example:

```bash
export TF_VAR_repository_secrets='{
  "EVIDARA_PLATFORM_CONTROL_API_KEY": "…",
  "EVIDARA_LEGAL_SEARCH_API_KEY": "…"
}'
```

**Do not** put **Google Cloud Run IAM ID tokens** (`gcloud auth print-identity-token --audiences=…`) in `repository_secrets`: they expire in about an hour. For CI, [`.github/workflows/evidara-cli-remote-smoke.yml`](../../../.github/workflows/evidara-cli-remote-smoke.yml) mints fresh tokens using the **GitHub Environment** secrets `GCP_WORKLOAD_IDENTITY_PROVIDER` and `GCP_SERVICE_ACCOUNT_DEV` / `GCP_SERVICE_ACCOUNT_STAGING` (same pattern as e2e smoke).

For the staging smoke workflow, ensure these GitHub settings are present:

- Repository variables:
  - `GCP_PROJECT_ID_STAGING`
  - `DI_SURFACES_ROOT_URI_STAGING`
  - `SMOKE_SEED_URL_STAGING` (optional)
  - `SMOKE_REQUEST_TIMEOUT_SECONDS_STAGING` (optional)
- Environment `staging` secrets:
  - `GCP_WORKLOAD_IDENTITY_PROVIDER`
  - `GCP_SERVICE_ACCOUNT_STAGING`
  - `E2E_SMOKE_STAGING_SLACK_WEBHOOK` (optional)

## Notes

- Secret values are write-only in GitHub and should be treated as sensitive in Terraform state.
- Prefer OIDC-based auth paths (no static cloud service account keys).
- If environments/variables already exist from manual `gh` commands, either import them into Terraform state before first apply or remove them once and let Terraform recreate/manage them.
- As an alternative to Terraform apply for quick operational sync, use [`../../../../scripts/sync-github-cd-config.sh`](../../../../scripts/sync-github-cd-config.sh) and start with `--interactive --preflight`.
