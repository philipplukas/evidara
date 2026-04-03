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

## What does not exist yet

- Databricks workflow wiring
- Pub/Sub subscription / deployment wiring for the runtime ingress service
- Spark-native Delta writes and Unity Catalog table/view creation automation
- Terraform and Databricks bundle deploy/promotion integration in CI/CD
- Policy Resolver YAML rules and source-profile registry
- spaCy or comparable NLP pipeline stages
- Docling integration for structured content extraction
- Citation extraction
- Canonical jurisdiction assignment
- RIS-specific XML schema tuning beyond the current heuristic path

## Local setup

```bash
cd document-intelligence
python3 -m pip install -e ".[dev]"
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

## Optional Delta sink configuration

Set these together to switch the CLI path from the in-memory sink to the Delta sink:

- `DI_PUBLISHED_DOCUMENTS_URI`
- `DI_PUBLISHED_SECTIONS_URI`
- `DI_PROCESSING_MANIFESTS_URI`

Optional:

- `DI_PROCESSING_VERSION`

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
