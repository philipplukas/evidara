# Environment Variable Files

Per-environment Terraform variable files live here.

Current scaffold:

- [`dev/document_intelligence.databricks.tfvars`](dev/document_intelligence.databricks.tfvars)
- [`staging/document_intelligence.databricks.tfvars`](staging/document_intelligence.databricks.tfvars)
- [`prod/document_intelligence.databricks.tfvars`](prod/document_intelligence.databricks.tfvars)

These files contain non-secret environment scaffolding only.
Do not commit credentials or secret values here.
