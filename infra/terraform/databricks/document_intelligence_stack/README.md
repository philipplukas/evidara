# Document Intelligence Databricks Stack

Top-level Terraform stack for provisioning the Databricks/Unity Catalog layer used by `document-intelligence`.

## What this owns

- Databricks provider configuration for one workspace
- environment-specific naming defaults for the DI catalog and external location
- invocation of the reusable module under [`../document_intelligence/`](../document_intelligence/)

## What this expects

- an environment tfvars file from [`../../../env/`](../../../env/)
- an existing Unity Catalog storage credential
- the Databricks Asset Bundle and SQL/bootstrap flow to be deployed separately

## Typical usage

From the repository root:

```bash
terraform -chdir=infra/terraform/databricks/document_intelligence_stack init
terraform -chdir=infra/terraform/databricks/document_intelligence_stack plan \
  -var-file=../../../env/dev/document_intelligence.databricks.tfvars
```

Switch the `-var-file` target to `staging` or `prod` for the other environments.

## Naming defaults

If no overrides are provided, the stack derives:

- catalog: `evidara_document_intelligence_<env>`
- schema: `published`
- external location: `evidara_document_intelligence_surfaces_<env>`

Those defaults keep the environment split explicit while letting the leaf module stay reusable.

## Optional compute guardrails

Set `enable_databricks_compute_guardrails = true` in the environment tfvars to create a workspace **cluster policy** named `Evidara compute guardrails` that caps per-cluster DBU/hour and worker count, and grants **CAN_USE** on that policy to the `users` group (override with `databricks_guardrails_grant_can_use_group`).

The **Databricks Asset Bundle** under `document-intelligence/` resolves `compute_guardrails_policy_id` via a bundle variable **lookup** on that policy name and sets `policy_id` on every job `new_cluster`. Apply Terraform in each workspace **before** `databricks bundle validate` / `deploy`, or validation fails when the policy is missing. To unblock CI without the policy yet, pass an explicit id: `--var compute_guardrails_policy_id=<policy-id>` (optional GitHub secret `DATABRICKS_COMPUTE_GUARDRAILS_POLICY_ID` in `document-intelligence-cd.yml`).

**CLI tokens:** use `eval "$(scripts/export-databricks-auth-env.sh -p <profile>)"` before `terraform apply` (no manual PAT copy). To populate that GitHub secret from the workspace, run `scripts/sync-databricks-cluster-policy-github-secret.sh` (see `document-intelligence/databricks/README.md`).
