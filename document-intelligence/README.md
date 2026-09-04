# Document Intelligence

Initial Python scaffold for the Evidara `document-intelligence` component.

## What exists

- Tolerant parsing of `artifact_bundle.available` events
- Pub/Sub push-envelope decoding for the local CLI entrypoint
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
- SQL renderers for published-surface, bronze, and governance registration under [`src/document_intelligence/bootstrap/`](src/document_intelligence/bootstrap/)
- Optional parser/NLP runtime flags (`DI_PARSER_BACKEND`, `DI_ENABLE_SPACY`) with safe defaults
- Optional `llm` dependency group plus extractor package scaffold under [`src/document_intelligence/extractors/`](src/document_intelligence/extractors/)
- Initial dbt scaffold under [`dbt/`](dbt/)

## What does not exist yet

- Spark-native Delta writes and automated catalog table/view creation
- dbt run/test execution against a real SQL warehouse in CI
- Citation extraction
- Canonical jurisdiction assignment
- RIS-specific XML schema tuning beyond the current heuristic path
- LLM extractor pipeline integration and runtime configuration

## Local setup

> **Two dependency sets, on purpose (#848).** `uv.lock` is what the **images** install
> (`uv sync --frozen` in all three Dockerfiles) and what `uv run` gives you locally, on the
> Python in `.python-version` (3.12, matching the base image). The `pip install -e ".[...]"`
> commands below resolve `pyproject.toml`'s **floors** against PyPI on the day you run them,
> which is what CI's `document-intelligence-check` job does as an early warning. They are not
> the same software: on 2026-09-03 the floors gave `deltalake` 1.6.3 / `pyarrow` 25.0.1 and the
> lock gave 1.5.0 / 23.0.1. **To reproduce what production runs, use `uv run`.** Changing a
> floor without re-locking now fails `uv sync --frozen`, in CI and in the image build.

Minimal lint + editor tooling:

```bash
cd document-intelligence
python3 -m pip install -e ".[dev]"
```

Match **CI / pre-commit** (Ruff + pytest + service deps + dbt gate via repo script):

```bash
cd document-intelligence
python3 -m pip install -e ".[dev,service,test]"
```

The optional **`test`** extra adds `pytest` and is used by `scripts/check-document-intelligence.sh` and by the repo-root workflow `.github/workflows/eval-ris.yml` (`pip install -e "./document-intelligence[test]"`).

For experimental LLM extractor work, add the `llm` extra:

```bash
cd document-intelligence
python3 -m pip install -e ".[dev,service,test,llm]"
```

## Local quality gate

```bash
bash scripts/check-document-intelligence.sh
```

## Event input shape

The local CLI and the runtime ingress service accept either:

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
- `document_intelligence_delta_projection_backfill` to rebuild the legal-search
  OpenSearch index from canonical Delta (ADR-0005). It replays each
  `published_documents` row as a `document.processed` event through the normal
  projections endpoint, so it is idempotent, resumable (`--resume`), and safe to
  run against a live read alias. This is the recovery path when the search index
  is lost — see
  [docs/runbooks/projection-reindex-backfill.md](../docs/runbooks/projection-reindex-backfill.md).

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

You can also derive all three published surface URIs from a single root by setting `DI_SURFACES_ROOT_URI` instead.

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
