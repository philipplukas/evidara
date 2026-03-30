# Document Intelligence

Initial Python scaffold for the Evidara `document-intelligence` component.

## What exists

- Tolerant parsing of `artifact_bundle.available` events
- Bundle-manifest and artifact loading for `file://`, plain filesystem paths, and `gs://`
- Minimal HTML normalization into a shared IR and section extraction from that IR
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

## What does not exist yet

- Databricks workflow wiring
- Spark-native Delta writes and Unity Catalog table/view creation automation
- Terraform apply/deploy integration in CI/CD
- Citation extraction
- Canonical jurisdiction assignment
- XML-specific normalization and parsing

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

You can also derive all three published surface URIs from a single root by setting:

- `DI_SURFACES_ROOT_URI`
