# Document Intelligence Testing

## Scope

Testing strategy for the document-intelligence component, which owns:

- artifact bundle ingestion
- parsing and normalization
- section construction
- canonical document creation
- processing manifests
- publication events
- quality checks

The MVP test plan assumes bundle ingestion, canonical `Document`, `Section`, and `ProcessingManifest` outputs are implemented first. Citation extraction and canonical jurisdiction assignment are added once those capabilities are implemented.

---

## Minimal Tests for MVP

### Unit tests

- HTML/XML normalization helpers
- section title extraction and ordering
- source/jurisdiction profile dispatch
- content-type and artifact-role selection
- HTML tag stripping / normalization
- Section title extraction from headings
- Content type detection

#### Section construction logic

- Sections are created in correct order
- Section depth and parent references are valid if hierarchical sections are enabled
- Empty sections are handled (skipped or flagged)

### Schema Validation

- Pipeline-produced `Document` output conforms to JSON Schema
- Pipeline-produced `Section` output conforms to JSON Schema
- Pipeline-produced `ProcessingManifest` output conforms to JSON Schema
- `artifact_bundle.available`, `document.processed`, and `document.processing_status.updated` conform to event schemas
- Repo examples under `contracts/examples/` for `Document`, `Section`, `ProcessingManifest`, and the current DI event set validate against locally resolved schemas without network access

Add `Citation` schema validation once citation extraction is implemented.

### Golden Document Tests

Use representative bundles from `tests/golden/`.

Current golden matrix:

- `simple_html`
- `messy_html`
- `nested_headings`
- `no_heading_fallback`
- `ris_xml`
- `invalid_no_primary`

For each golden bundle, assert:

- at least one `Document` revision is created
- section count is within expected range
- key sections are present
- provenance is populated
- `document_revision` increments correctly
- lifecycle status and required canonical timestamps are populated
- published refs are present when status is `canonical_ready`

Add citation count and canonical jurisdiction assertions once those capabilities are implemented.

### Invariant checks

| Invariant | Description |
|-----------|-------------|
| Provenance present | `document.provenance.source_id`, `run_id`, and `corpus_id` are populated |
| Document revisions monotonic | newer canonical publications use higher `document_revision` |
| Sections ordered correctly | section ordinals are monotonically increasing |
| Section/document relations valid | every section references a valid `document_id` |
| Canonical-ready has published refs | `ProcessingManifest` includes exact refs when ready |
| Required fields present | `title`, `processed_at`, and `processing_manifest_id` are populated |
| No orphaned sections | Every section belongs to exactly one document revision |

### Minimal end-to-end processing path

1. Place a golden bundle in a test storage location
2. Trigger processing
3. Verify `Document`, `Section`, and `ProcessingManifest` rows are written
4. Verify `document.processing_status.updated` and `document.processed` behaviors are validated for the relevant lifecycle path
5. Verify lineage is traceable

The default local quality gate for this component is [`../../../scripts/check-document-intelligence.sh`](../../../scripts/check-document-intelligence.sh). It runs Ruff plus the full unittest suite and should match the GitHub Actions check.

### Adapter coverage

- GCS bundle loader tests use a stubbed storage client and verify manifest/artifact reads plus checksum enforcement
- Delta sink tests write to temporary Delta tables and read them back to verify published rows and replay-safe appends
- CLI smoke tests exercise the bundle-processing entrypoint with local fixtures
- Event-ingest tests cover both direct `artifact_bundle.available` payloads and Pub/Sub push envelopes with base64-decoded event JSON
- Runtime consumer HTTP tests cover successful Pub/Sub-style ingestion, invalid envelope rejection, and optional bearer protection
- Databricks runtime tests validate the wrapper configuration plus a local Delta-backed bundle run using the Databricks-style entrypoint
- Bootstrap asset tests verify the published-surface SQL renderer and Terraform module shape for the Unity Catalog scaffolding path
- Bootstrap asset tests also verify the top-level Databricks stack wiring and the presence of `dev` / `staging` / `prod` tfvars for the DI Terraform path
- XML bundle tests verify RIS-style section labels and extracted metadata survive canonicalization

---

## Drift Checks

| Check | What it catches |
|-------|----------------|
| Average section count changes sharply | Source format changed or parser broke |
| Title or lifecycle-status null rate spikes | Metadata extraction degraded |
| Expected headings disappear in golden docs | Parser no longer handles known patterns |
| Published-ref readiness mismatches | Manifest lifecycle drifted from publication behavior |

Add citation-count and jurisdiction-quality drift checks once those capabilities are implemented.

---

## Confidence Goal

These tests should answer:

- **Can we trust canonical outputs enough for indexing and research?** — Golden tests, invariants, and schema validation ensure output quality.
- **Can we detect semantic degradation even when the pipeline still runs?** — Drift checks and golden comparisons catch silent quality loss.

---

## What NOT to Overbuild Early

- Do not build exhaustive parser tests for every HTML variant — test the patterns that matter via golden samples
- Do not build fuzzing or property-based testing yet — add when processing is stable
- Do not test PDF rendering or complex format handling until those source families are actually in use
- Do not build performance benchmarks — correctness first
- Do not attempt full NLP quality metrics — coarse assertions on golden samples are sufficient for MVP

---

## Later Expansion

| Phase | Addition |
|-------|---------|
| Post-MVP | Citation schema tests and citation golden assertions |
| Post-MVP | Jurisdiction assignment assertions and drift checks |
| Post-MVP | Expanded golden set (per source family) |
| Post-MVP | Processing performance benchmarks |
| Later | Property-based tests for parser edge cases |
| Later | Quality scoring with threshold alerts |
| Later | Full distribution monitoring for semantic drift |
