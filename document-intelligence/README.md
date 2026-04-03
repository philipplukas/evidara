# Document Intelligence

Initial Python scaffold for the Evidara `document-intelligence` component.

## What exists

- Tolerant parsing of `artifact_bundle.available` events
- Bundle-manifest and artifact loading for `file://`, plain filesystem paths, and `gs://`
- Minimal HTML and XML normalization into a shared IR and section extraction from that IR
- Contract-shaped `Document`, `Section`, and `ProcessingManifest` models
- Contract-shaped `document.processing_status.updated` and `document.processed` event builders
- In-memory published-surface sink for fast tests
- Delta-backed published-surface sink for `published_documents`, `published_sections`, and `processing_manifests`
- Explicit published surface definitions for documents, sections, and processing manifests
- Offline JSON Schema validation helpers against repo `contracts/`
- Golden bundle fixtures plus GCS, Delta, CLI, and contract tests
- A simple processing job entrypoint with env-driven sink selection
- A Databricks-oriented runtime entrypoint plus Databricks Asset Bundle scaffolding under [`databricks/`](databricks/)
- Terraform stubs for Unity Catalog scaffolding under [`../infra/terraform/databricks/document_intelligence/`](../infra/terraform/databricks/document_intelligence/)
- A top-level Databricks Terraform stack plus `dev` / `staging` / `prod` tfvars under [`../infra/terraform/databricks/document_intelligence_stack/`](../infra/terraform/databricks/document_intelligence_stack/) and [`../infra/env/`](../infra/env/)
- SQL/bootstrap assets for published surface registration under [`databricks/sql/`](databricks/sql/)
- Optional parser/NLP runtime flags (`DI_PARSER_BACKEND`, `DI_ENABLE_SPACY`) with safe defaults
- Initial dbt scaffold under [`dbt/`](dbt/)
- Databricks resource wiring for canonical processing, bronze autoloader bootstrap, dbt transformations, and smoke jobs under [`resources/`](resources/)

## What does not exist yet

- Spark-native Delta writes and Unity Catalog table/view creation automation
- Databricks bundle validate/deploy automation in CI/CD
- Terraform apply/deploy automation in CI/CD
- dbt run/test execution against a real Databricks SQL Warehouse in CI
- Citation extraction
- Canonical jurisdiction assignment
- RIS-specific XML schema tuning beyond the current heuristic path

## Local test run

```bash
cd document-intelligence
python3 -m unittest discover -s tests -v
```

## Optional Delta sink configuration

Set these together to switch the CLI path from the in-memory sink to the Delta sink:

- `DI_PUBLISHED_DOCUMENTS_URI`
- `DI_PUBLISHED_SECTIONS_URI`
- `DI_PROCESSING_MANIFESTS_URI`

Optional:

- `DI_PROCESSING_VERSION`
- `DI_PARSER_BACKEND` (`legacy` by default, optional `docling` scaffold path)
- `DI_ENABLE_SPACY` (`false` by default)
- `DI_SPACY_MODEL_NAME` (`xx_sent_ud_sm` by default)
- `DI_SPACY_MAX_CHARS_PER_SECTION` (`100000` by default)
- `DI_SPACY_BATCH_SIZE` (`32` by default)

## dbt validation

The repository check script now validates dbt package resolution and project parsing:

```bash
bash scripts/check-document-intelligence.sh
```

The check currently runs:

- JSON Schema validation for shared contracts and examples
- `unittest` suite for `document-intelligence`
- `dbt deps` + `dbt parse` (target `dev`) using [`dbt/profiles.yml`](dbt/profiles.yml)

## Databricks Asset Bundle targets

The bundle currently defines these targets:

- `dev`
- `staging`
- `prod`

Validate a target locally:

```bash
cd document-intelligence
databricks bundle validate -t staging
```

You can also derive all three published surface URIs from a single root by setting:

- `DI_SURFACES_ROOT_URI`
