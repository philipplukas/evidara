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

### CLI auth (no pasted PATs in the shell history)

0. **One-shot login check** (optional): prompts for **gh**, **gcloud** (and optional ADC), and **databricks** profiles `dev` / `staging` / `prod`:

   ```bash
   ../scripts/ensure-evidara-cli-auth.sh
   ```

1. **Databricks** (Terraform + bundle): use the official CLI so tokens stay short-lived where possible.

   ```bash
   databricks auth login   # or: databricks configure --token (legacy)
   ```

   Then load host + token for the profile you use for **dev** (repeat with other profiles for staging/prod):

   ```bash
   eval "$(../scripts/export-databricks-auth-env.sh --profile dev)"
   ```

   Run Terraform from the repo root with that environment in your shell, or pass the same exports into CI.

2. **GitHub Actions** optional policy override: after the guardrails policy exists in the workspace, push its id into the environment secret using **Databricks + gh** CLIs (no UI copy/paste):

   ```bash
   ../scripts/sync-databricks-cluster-policy-github-secret.sh --env dev --profile dev --apply
   ```

3. **GCP** identity tokens for Cloud Run are already scripted as `../scripts/mint-cloud-run-tokens.sh` (see [docs/setup/gcp-local-cloud-run-auth.md](../../docs/setup/gcp-local-cloud-run-auth.md)).

4. **Bulk GitHub CD sync** (variables + `DATABRICKS_*` secrets from GSM or CLI profiles): `../scripts/sync-github-cd-config.sh --help`

Typical commands from the `document-intelligence/` directory:

```bash
cd ..
bash scripts/check-document-intelligence-runtime.sh

# then deploy from the component directory
eval "$(../scripts/export-databricks-auth-env.sh --profile dev)"
cd document-intelligence
databricks bundle validate -t dev
databricks bundle validate -t staging
databricks bundle validate -t prod
databricks bundle deploy -t dev
databricks bundle deploy -t staging
databricks bundle deploy -t prod
databricks bundle run -t dev document_intelligence_process_bundle --params event_path=/Workspace/...
```

Bundle authentication comes from `DATABRICKS_HOST` and `DATABRICKS_TOKEN`
(`export-databricks-auth-env.sh` locally, GitHub Environment secrets in CI).
The checked-in targets mirror the tracked Terraform env files for:

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

1. Plan/apply the stack in [`../../infra/terraform/databricks/document_intelligence_stack/`](../../infra/terraform/databricks/document_intelligence_stack/) with an env file from [`../../infra/env/`](../../infra/env/). When `enable_databricks_compute_guardrails` is true, this creates the cluster policy **`Evidara compute guardrails`** that the bundle resolves by name for every job cluster.
2. Deploy the Asset Bundle job (`databricks bundle validate` / `deploy` need that policy to exist in the workspace, unless you override `compute_guardrails_policy_id` with `--var`).
3. Run the DI job so Delta data lands at the published-surface root.
4. Register the published surfaces using the bootstrap SQL.
