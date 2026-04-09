# Document Intelligence

Initial Python scaffold for the Evidara `document-intelligence` component.

## What exists

- Tolerant parsing of `artifact_bundle.available` events
- Pub/Sub push-envelope decoding for the local CLI and Databricks entrypoints
- Internal HTTP runtime ingress for Pub/Sub-style event delivery
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
- Optional `llm` dependency group plus extractor package scaffold under [`src/document_intelligence/extractors/`](src/document_intelligence/extractors/)
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
- LLM extractor pipeline integration and runtime configuration

## Local setup

```bash
cd document-intelligence
python3 -m pip install -e ".[dev]"
```

For experimental LLM extractor work, install the optional extra instead:

```bash
cd document-intelligence
python3 -m pip install -e ".[dev,llm]"
```

## Local quality gate

```bash
bash scripts/check-document-intelligence.sh
```

## Runtime / deployment validation

```bash
bash scripts/check-document-intelligence-runtime.sh
```

The Databricks bundle now carries checked-in `dev`, `staging`, and `prod` targets that mirror the tracked Terraform environment inputs for the published surface root and workspace host.

## Event input shape

The local CLI, Databricks entrypoint, and runtime ingress service now accept either:

- a raw `artifact_bundle.available` JSON payload
- a Pub/Sub push envelope whose `message.data` contains base64-encoded event JSON

That keeps local execution aligned with the eventual subscription payload shape without requiring a live subscriber yet.

## Optional service extras

Install the HTTP services and their tests with:

```bash
cd document-intelligence
python3 -m pip install -e ".[dev,service]"
```

Available entrypoints:

- `document_intelligence_document_service` for the read-oriented document service
- `document_intelligence_runtime_ingress` for the internal event-processing ingress

## Optional LLM extraction extras

The `llm` extra installs DSPy and hosted-model clients for upcoming
LLM-assisted extraction work:

```bash
cd document-intelligence
python3 -m pip install -e ".[llm]"
```

Today this only provides the dependency set and the
[`extractors/`](src/document_intelligence/extractors/) package scaffold. It
does not yet switch the main processing pipeline away from the existing
deterministic path.

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
- `DI_ENABLE_LLM_EXTRACTOR` (`false` by default; currently only activates the guarded extractor seam)
- `DI_LLM_CONFIDENCE_THRESHOLD` (`0.7` by default)

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

## Always-on runtime consumer

Consume `artifact_bundle.available` from Pub/Sub and emit status/publication events:

```bash
document_intelligence_runtime_consumer \
  --project-id evidara-dev \
  --subscription-name document-intelligence-artifact-bundle-available
```

Use `--dry-run-publish` for local replay without outbound event publication.

Containerized runtime deployments can use `document-intelligence/Dockerfile` with:

- `DI_GCP_PROJECT_ID`
- `DI_SUBSCRIPTION_NAME` (optional; defaults to `document-intelligence-artifact-bundle-available`)
- `DI_STATUS_TOPIC_NAME` (optional; defaults to `document-processing-status-updated`)
- `DI_PROCESSED_TOPIC_NAME` (optional; defaults to `document-processed`)
