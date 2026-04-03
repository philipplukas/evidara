# Environment Variable Files

Per-environment Terraform variable files live here.

Current scaffold:

- [`dev/document_intelligence.databricks.tfvars`](dev/document_intelligence.databricks.tfvars)
- [`staging/document_intelligence.databricks.tfvars`](staging/document_intelligence.databricks.tfvars)
- [`prod/document_intelligence.databricks.tfvars`](prod/document_intelligence.databricks.tfvars)
- [`dev/runtime.gcp.tfvars.example`](dev/runtime.gcp.tfvars.example)
- [`staging/runtime.gcp.tfvars.example`](staging/runtime.gcp.tfvars.example)
- [`prod/runtime.gcp.tfvars.example`](prod/runtime.gcp.tfvars.example)
- [`dev/opensearch.gke.tfvars.example`](dev/opensearch.gke.tfvars.example)
- [`staging/opensearch.gke.tfvars.example`](staging/opensearch.gke.tfvars.example)
- [`prod/opensearch.gke.tfvars.example`](prod/opensearch.gke.tfvars.example)
- [`github.repo_settings.tfvars.example`](github.repo_settings.tfvars.example)
- [`github_cd_bootstrap.gcp.tfvars.example`](github_cd_bootstrap.gcp.tfvars.example)

These files contain non-secret environment scaffolding only.
Do not commit credentials or secret values here.

## Secret and env handling flow

Use this flow for each environment (`dev`, `staging`, `prod`):

1. Apply Terraform to create or update infrastructure resources and secret containers.
2. Add secret values as Secret Manager versions (outside Terraform state).
3. Deploy or roll Cloud Run revisions so services read the newest secret versions.
4. Verify health, connectivity, and core event flow.

### Rules

- Never commit secret values to `*.tfvars`, `.env`, or docs.
- Keep non-sensitive runtime config in Terraform variables.
- Keep sensitive values in Secret Manager and rotate with new versions.
- For OpenSearch, keep secret IDs stable:
  - `opensearch-node-{env}`
  - `opensearch-username-{env}`
  - `opensearch-password-{env}`

### Cloud Run private egress assumptions

Runtime tfvars support optional private egress assumptions:

- `runtime_vpc_access_connector`
- `runtime_vpc_egress` (`PRIVATE_RANGES_ONLY` or `ALL_TRAFFIC`)

For OpenSearch on GKE, set `runtime_vpc_access_connector` using output `vpc_connector_id` from `infra/terraform/opensearch/gke_stack`.

### OpenSearch secret sync helper

After applying the OpenSearch GKE stack, sync stack outputs into Secret Manager:

```bash
python3 scripts/sync_opensearch_secrets.py \
  --project-id <project-id> \
  --env dev \
  --opensearch-stack-dir infra/terraform/opensearch/gke_stack
```

Preview without writing versions:

```bash
python3 scripts/sync_opensearch_secrets.py \
  --project-id <project-id> \
  --env dev \
  --dry-run
```
