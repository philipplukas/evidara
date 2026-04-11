# Environment Variable Files

Per-environment Terraform variable files live here.

Current scaffold:

- [`dev/document_intelligence.databricks.tfvars`](dev/document_intelligence.databricks.tfvars)
- [`staging/document_intelligence.databricks.tfvars`](staging/document_intelligence.databricks.tfvars)
- [`prod/document_intelligence.databricks.tfvars`](prod/document_intelligence.databricks.tfvars)
- [`dev/runtime.gcp.tfvars.example`](dev/runtime.gcp.tfvars.example)
- [`dev/runtime.gcp.ci.tfvars`](dev/runtime.gcp.ci.tfvars)
- [`staging/runtime.gcp.tfvars.example`](staging/runtime.gcp.tfvars.example)
- [`staging/runtime.gcp.ci.tfvars`](staging/runtime.gcp.ci.tfvars)
- [`prod/runtime.gcp.tfvars.example`](prod/runtime.gcp.tfvars.example)
- [`dev/opensearch.gke.tfvars.example`](dev/opensearch.gke.tfvars.example)
- [`staging/opensearch.gke.tfvars.example`](staging/opensearch.gke.tfvars.example)
- [`prod/opensearch.gke.tfvars.example`](prod/opensearch.gke.tfvars.example)

These files contain non-secret environment scaffolding only.
Do not commit credentials or secret values here.

## Spend and compute guardrails (optional)

- **GCP (runtime stack):** set `enable_billing_budget = true` plus `billing_account_id` and amount/currency in `runtime.gcp.tfvars` to create a **project-scoped Cloud Billing budget** with percentage alerts. Billing admins receive alerts by default; set `billing_budget_notification_emails` to also create Monitoring email channels (max five). See `infra/terraform/gcp/runtime_stack/billing_guardrails.tf`. Defaults stay off so CI and fresh clones do not require billing APIs.
- **Databricks (document intelligence stack):** set `enable_databricks_compute_guardrails = true` in `document_intelligence.databricks.tfvars` to create the workspace cluster policy **`Evidara compute guardrails`**. The `document-intelligence` Asset Bundle resolves it by name and sets `policy_id` on every job `new_cluster`; apply Terraform before `databricks bundle validate` / `deploy`, or pass `--var compute_guardrails_policy_id=...` (see `document_intelligence_stack` README and `document-intelligence-cd.yml`).

## Secret and env handling flow

Use this flow for each environment (`dev`, `staging`, `prod`):

1. Apply Terraform to create/update infrastructure resources, Secret Manager secret containers, IAM, and Cloud Run wiring.
2. Add secret **values** as Secret Manager versions (outside Terraform state):
   - Upstream-provided values: Firecrawl API key, OpenSearch endpoint/credentials.
   - Internal-generated values: service bearer tokens, internal webhook shared secrets, DB password (if managed by platform).
3. Deploy or roll Cloud Run revisions so services read the newest secret versions.
   - For private OpenSearch access, set `vpc_connector` and `vpc_egress` in each runtime `cloud_run_services` entry.
4. Verify health and core event flow.

### Rules

- Never commit secret values to `*.tfvars`, `.env` files in git, or docs.
- Keep non-sensitive runtime config in Terraform `env_vars`.
- Keep sensitive values in Secret Manager via `secret_env_vars`.
- Rotate by adding a new secret version, redeploying/rolling revisions, then revoking old upstream credentials.

### Helper script

Use `scripts/manage_runtime_secrets.py` to create missing secret containers and add versions with hidden prompts:

```bash
python3 scripts/manage_runtime_secrets.py \
  --project-id project-dacd6b7b-dc96-4534-b82 \
  --env dev
```

Optional: process only selected secrets:

```bash
python3 scripts/manage_runtime_secrets.py \
  --project-id project-dacd6b7b-dc96-4534-b82 \
  --env dev \
  --only firecrawl-api-key firecrawl-webhook-secret
```

Load OpenSearch values directly from a local `.env` file:

```bash
python3 scripts/manage_runtime_secrets.py \
  --project-id project-dacd6b7b-dc96-4534-b82 \
  --env dev \
  --only opensearch-node opensearch-username opensearch-password \
  --from-env-file /path/to/.env
```

### Firecrawl runtime helper

Firecrawl account settings are not fully Terraform-managed. Use this helper after Cloud Run deploy to derive and wire the webhook URL:

```bash
python3 scripts/configure_firecrawl_runtime.py \
  --project-id project-dacd6b7b-dc96-4534-b82 \
  --region europe-west6 \
  --env dev \
  --tfvars-path infra/env/dev/runtime.gcp.tfvars
```

Optional: send a signed test callback using the current webhook secret:

```bash
python3 scripts/configure_firecrawl_runtime.py \
  --project-id project-dacd6b7b-dc96-4534-b82 \
  --region europe-west6 \
  --env dev \
  --verify-callback
```

## First-slice runtime service set

For the first end-to-end slice, keep these Cloud Run services present in each environment tfvars:

- `platform-control-api`
- `platform-control-worker`
- `document-intelligence-consumer`
- `legal-search-api`

The runtime stack defaults already include Pub/Sub subscription wiring for DI ingestion and legal-search projection push callbacks; do not remove those subscriptions unless replacing them with an equivalent delivery path.

### Acquisition dispatch and control-panel deep link

- When `platform-control-worker` is in use, set `PLATFORM_CONTROL_RUN_DISPATCH_BACKEND=worker` on **`platform-control-api`** so new runs stay `PENDING` until the worker calls providers (see `runtime.gcp.tfvars.example` for dev/staging).
- Set `NEXT_PUBLIC_CONTROL_PANEL_URL` on **`legal-search-frontend`** to the public URL of `platform-control-admin` so the search header can show the control-panel entrypoint (see the same tfvars examples).

### GKE OpenSearch secret sync

After applying the self-managed OpenSearch GKE stack, sync stack outputs into GCP Secret Manager:

```bash
python3 scripts/sync_opensearch_secrets.py \
  --project-id project-dacd6b7b-dc96-4534-b82 \
  --env dev \
  --opensearch-stack-dir infra/terraform/opensearch/gke_stack
```

Preview without writing secret versions:

```bash
python3 scripts/sync_opensearch_secrets.py \
  --project-id project-dacd6b7b-dc96-4534-b82 \
  --env dev \
  --dry-run
```
