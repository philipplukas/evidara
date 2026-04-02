# Databricks Runtime Slice

This directory documents the first Databricks-oriented runtime packaging for `document-intelligence`.

## Files

- `../databricks.yml`: Databricks Asset Bundle root for the component
- `../resources/document_intelligence_job.yml`: Lakeflow Job definition for bundle processing
- `sql/README.md`: Published-surface SQL/bootstrap guidance
- [`../../infra/terraform/databricks/document_intelligence_stack/`](../../infra/terraform/databricks/document_intelligence_stack/): top-level Terraform stack for one Databricks workspace/environment
- [`../../infra/terraform/databricks/document_intelligence/`](../../infra/terraform/databricks/document_intelligence/): Terraform module for Unity Catalog scaffolding

## Runtime model

- The job runs the existing wheel-based pipeline through the `run` entrypoint in `document_intelligence.jobs.databricks_process_event`.
- The task expects:
  - `event_path`
  - `processing_version`
  - `surfaces_root_uri`
- The runtime writes Delta outputs under:
  - `${surfaces_root_uri}/published_documents`
  - `${surfaces_root_uri}/published_sections`
  - `${surfaces_root_uri}/processing_manifests`

## Validation and deployment

Typical commands from the `document-intelligence/` directory:

```bash
databricks bundle validate -t dev
databricks bundle deploy -t dev
databricks bundle run -t dev document_intelligence_process_bundle --params event_path=/Workspace/...,surfaces_root_uri=gs://...
```

This slice does not yet include:

- Spark-native processing or sink implementations
- XML parsing or citation extraction

## Ownership split

- Databricks Asset Bundle: owns the DI job packaging and deployment shape
- Terraform: owns the stable Unity Catalog scaffolding
- SQL/bootstrap helper: registers the published Delta surfaces after the job has produced data

Typical infra flow:

1. Plan/apply the stack in [`../../infra/terraform/databricks/document_intelligence_stack/`](../../infra/terraform/databricks/document_intelligence_stack/) with an env file from [`../../infra/env/`](../../infra/env/).
2. Deploy the Asset Bundle job.
3. Run the DI job so Delta data lands at the published-surface root.
4. Register the published surfaces using the bootstrap SQL.
