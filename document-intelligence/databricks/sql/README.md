# DDL Bootstrap

This directory documents the SQL/bootstrap path for creating document-intelligence tables in Unity Catalog. Two layers are bootstrapped, each from a Python module that renders idempotent SQL.

## Layout

- `bronze` — Auto Loader landing tables (owned by `bootstrap/bronze_schemas.py`).
- `published` — canonical DI surfaces written by the runtime and registered as external Delta tables (owned by `persist/surfaces.py`, rendered by `bootstrap/register_surfaces.py`).

## Why this exists

The Delta datasets are physically written by the DI runtime (published) or by the Auto Loader notebook (bronze), but we do not want Terraform to own the evolving table metadata during early development.

The split is:

- Terraform creates the stable Unity Catalog scaffolding (catalog, external location, storage credential, grants).
- The bootstrap DDL step creates schemas and tables.
- The DI job / Auto Loader writes Delta data.

## Render the SQL

From [`../`](../):

```bash
# Bronze landing tables
document_intelligence_render_bronze_sql \
  --catalog-name document_intelligence \
  --schema-name bronze

# Published surface registrations
document_intelligence_render_surface_sql \
  --catalog-name document_intelligence \
  --schema-name published \
  --surfaces-root-uri gs://evidara-di-dev/published
```

Equivalent module invocations:

```bash
python3 -m document_intelligence.bootstrap.register_bronze --catalog-name ... --schema-name bronze
python3 -m document_intelligence.bootstrap.register_surfaces --catalog-name ... --schema-name published --surfaces-root-uri ...
```

## Apply the SQL in a workspace

Run the `document_intelligence_bootstrap_ddl` bundle job (see `resources/document_intelligence_bootstrap_job.yml`). It executes `databricks/notebooks/01_bootstrap_ddl.py`, which renders both SQL scripts in-process and issues each statement via `spark.sql`. Re-running is safe — every statement uses `CREATE SCHEMA / TABLE IF NOT EXISTS`.

## Runtime contract tests

Every published surface has a source-level `dbt_expectations.expect_table_columns_to_match_set` test attached in `dbt/models/sources_published.generated.yml`. The YAML is rendered from `src/document_intelligence/persist/surfaces.py` via:

```bash
document_intelligence_render_source_contracts \
  > dbt/models/sources_published.generated.yml
```

A unit test (`tests/test_bootstrap_assets.py::PublishedSourceContractsTests`) fails if the checked-in file drifts from the rendered output. The dbt source test fails at `dbt test` time if the runtime writes a column that is not in the contract, or stops writing one that is. `register_surfaces` additionally emits `ALTER TABLE ... SET TBLPROPERTIES` for each published surface to enable Change Data Feed and name-based column mapping (matching the bronze convention).

## Tables created

Bronze (managed Delta, populated by Auto Loader):

- `landing_envelopes`
- `document_processing_events`
- `raw_docling_output`
- `raw_nlp_annotations`
- `raw_metadata`
- `raw_documents`

Published (external Delta, populated by the DI runtime):

- `published_documents`
- `published_sections`
- `processing_manifests`
