# Databricks Terraform

This directory now has two layers for `document-intelligence`:

- [`document_intelligence/`](document_intelligence/) — reusable Unity Catalog module
- [`document_intelligence_stack/`](document_intelligence_stack/) — top-level stack with provider config and environment-aware defaults

Use the stack together with the per-environment tfvars files under [`../../env/`](../../env/) when planning or applying infra changes.
