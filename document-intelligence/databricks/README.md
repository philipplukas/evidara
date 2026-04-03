# Databricks Runtime Slice

This directory documents the first Databricks-oriented runtime packaging for `document-intelligence`.

## Files

- `../databricks.yml`: Databricks Asset Bundle root for the component
- `../resources/document_intelligence_job.yml`: Lakeflow Job definition for bundle processing
- `../resources/document_intelligence_autoloader_job.yml`: bronze ingest bootstrap job definition
- `../resources/document_intelligence_dbt_job.yml`: dbt transformation job definition
- `../resources/document_intelligence_smoke_job.yml`: smoke notebook job definition
- `sql/README.md`: Published-surface SQL/bootstrap guidance
- [`../../infra/terraform/databricks/document_intelligence_stack/`](../../infra/terraform/databricks/document_intelligence_stack/): top-level Terraform stack for one Databricks workspace/environment
- [`../../infra/terraform/databricks/document_intelligence/`](../../infra/terraform/databricks/document_intelligence/): Terraform module for Unity Catalog scaffolding

## Runtime model

- The job runs the existing wheel-based pipeline through the `run` entrypoint in `document_intelligence.jobs.databricks_process_event`.
- The task expects:
  - `event_path`
  - `processing_version`
  - `surfaces_root_uri`
  - `parser_backend` (`legacy` or `docling`)
  - `enable_spacy` (`true`/`false`)
  - `spacy_model_name`
  - `spacy_max_chars_per_section`
  - `spacy_batch_size`
- The runtime writes Delta outputs under:
  - `${surfaces_root_uri}/published_documents`
  - `${surfaces_root_uri}/published_sections`
  - `${surfaces_root_uri}/processing_manifests`

## Validation and deployment

Typical commands from the `document-intelligence/` directory:

```bash
cd ..
bash scripts/check-document-intelligence-runtime.sh

# then deploy from the component directory
cd document-intelligence
databricks bundle validate -t dev
databricks bundle validate -t staging
databricks bundle validate -t prod
databricks bundle deploy -t dev
databricks bundle deploy -t staging
databricks bundle deploy -t prod
databricks bundle run -t dev document_intelligence_process_bundle --params event_path=/Workspace/...
```

The checked-in targets mirror the tracked Terraform env files for:

- `workspace_host`
- `surfaces_root_uri`

That keeps the bundle and Unity Catalog stack aligned for `dev`, `staging`, and `prod`.

This slice does not yet include:

- Spark-native processing or sink implementations
- citation extraction

## Ownership split

- Databricks Asset Bundle: owns the DI job packaging and deployment shape
- Terraform: owns the stable Unity Catalog scaffolding
- SQL/bootstrap helper: registers the published Delta surfaces after the job has produced data

Typical infra flow:

1. Plan/apply the stack in [`../../infra/terraform/databricks/document_intelligence_stack/`](../../infra/terraform/databricks/document_intelligence_stack/) with an env file from [`../../infra/env/`](../../infra/env/).
2. Deploy the Asset Bundle job.
3. Run the DI job so Delta data lands at the published-surface root.
4. Register the published surfaces using the bootstrap SQL.
