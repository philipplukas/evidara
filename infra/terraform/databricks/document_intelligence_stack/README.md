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
