# Document Intelligence Databricks Terraform

Terraform module for the stable Databricks/Unity Catalog infrastructure around `document-intelligence`.

This is the reusable leaf module. In normal repo usage it is invoked by the top-level stack under [`../document_intelligence_stack/`](../document_intelligence_stack/), which owns the Databricks provider config and environment-specific defaults.

## What this manages

- Unity Catalog catalog
- Unity Catalog schema
- optional external location for the published surfaces root
- grants on the catalog, schema, and optional external location

## What this does not manage

- the Databricks Asset Bundle job itself
- published table registration
- table/view schema evolution

Those stay outside Terraform on purpose:

- the job is owned by the Databricks Asset Bundle under [`../../../../document-intelligence/databricks.yml`](../../../../document-intelligence/databricks.yml)
- published surface registration is handled by the SQL/bootstrap assets under [`../../../../document-intelligence/databricks/sql`](../../../../document-intelligence/databricks/sql)

## Why

Terraform is a strong fit for stable Unity Catalog objects and grants.
The published tables are expected to evolve more quickly during early DI work, so they are registered with SQL/bootstrap commands instead of being fully owned by Terraform.

## Typical flow

1. Apply the top-level stack under [`../document_intelligence_stack/`](../document_intelligence_stack/) with an environment tfvars file from [`../../../env/`](../../../env/).
2. Deploy the Databricks Asset Bundle job for `document-intelligence`.
3. Run the DI job so Delta data exists under the published surface root.
4. Run the published-surface bootstrap SQL to register:
   - `published_documents`
   - `published_sections`
   - `processing_manifests`
