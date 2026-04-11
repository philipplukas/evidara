# Databricks Terraform

This directory now has two layers for `document-intelligence`:

- [`document_intelligence/`](document_intelligence/) — reusable Unity Catalog module
- [`document_intelligence_stack/`](document_intelligence_stack/) — top-level stack with provider config and environment-aware defaults

Use the stack together with the per-environment tfvars files under [`../../env/`](../../env/) when planning or applying infra changes.

## CI/CD

The `terraform-databricks.yml` workflow automates fmt, plan, and apply for the `document_intelligence_stack`:

| Event | Jobs |
|-------|------|
| Pull request | `fmt-check`, `plan-dev`, `plan-staging` (plan output posted as PR comment) |
| Push to `main` | `apply-dev` → `apply-staging` → `apply-prod` (each gated by a repo variable) |
| `workflow_dispatch` with `run_apply=true` | All apply jobs |

### Required secrets (per environment)

| Secret | Description |
|--------|-------------|
| `DATABRICKS_HOST` | Databricks workspace URL (e.g. `https://dbc-xxx.cloud.databricks.com`) |
| `DATABRICKS_TOKEN` | Databricks personal access token or service-principal token |

### Apply gate variables

Set these repository or environment variables to enable CD apply:

| Variable | Scope | Purpose |
|----------|-------|---------|
| `TERRAFORM_DATABRICKS_APPLY_ENABLED` | repo | Enables `apply-dev` on push to `main` |
| `TERRAFORM_DATABRICKS_APPLY_ENABLED_STAGING` | repo | Gates promotion from dev → staging |
| `TERRAFORM_DATABRICKS_APPLY_ENABLED_PROD` | repo | Gates promotion to prod |

All three default to `false` (opt-in). Set to `'true'` when the environment is ready for automated apply.

### Ordering with bundle deploy

The `document-intelligence-cd.yml` workflow deploys the Databricks Asset Bundle (jobs, compute config). The Terraform stack creates the Unity Catalog catalog/schema/grants and the optional compute-guardrails cluster policy that the bundle references. Apply Terraform before running the bundle for a new environment, or ensure `COMPUTE_GUARDRAILS_POLICY_ID` is configured before the bundle deploy runs. See [`infra/env/README.md`](../../env/README.md) for details.
