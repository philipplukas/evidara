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
  "prod": {
    "GCP_WORKLOAD_IDENTITY_PROVIDER": "projects/123/locations/global/workloadIdentityPools/github/providers/evidara",
    "GCP_SERVICE_ACCOUNT_PROD": "gha-deployer-prod@evidara-prod.iam.gserviceaccount.com",
    "DATABRICKS_HOST": "https://dbc-yyyy.cloud.databricks.com",
    "DATABRICKS_TOKEN": "..."
  }
}'

terraform apply -var-file="../../../env/github.repo_settings.tfvars.example"
```

## Notes

- Secret values are write-only in GitHub and should be treated as sensitive in Terraform state.
- Prefer OIDC-based auth paths (no static cloud service account keys).
- If environments/variables already exist from manual `gh` commands, either import them into Terraform state before first apply or remove them once and let Terraform recreate/manage them.
- As an alternative to Terraform apply for quick operational sync, use [`../../../../scripts/sync-github-cd-config.sh`](../../../../scripts/sync-github-cd-config.sh) and start with `--interactive --preflight`.
