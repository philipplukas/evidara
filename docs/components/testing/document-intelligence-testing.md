# Document Intelligence Testing

## Scope

Testing strategy for the document-intelligence component, which owns:

- artifact bundle ingestion
- parsing and normalization
- section construction
- canonical document creation
- processing manifests
- publication events

## Minimal Tests for MVP

### Unit tests

- HTML/PDF normalization helpers
- section title extraction and ordering
- source/jurisdiction profile dispatch
- content-type and artifact-role selection

### Schema validation

- `Document` output conforms to JSON Schema
- `Section` output conforms to JSON Schema
- `ProcessingManifest` output conforms to JSON Schema
- `document.processed`, `document.processing_status.updated`, and `document.withdrawn` conform to event schemas

### Golden bundle tests

Use representative bundles from `tests/golden/`.

For each golden bundle, assert:

- at least one `Document` revision is created
- section count is within expected range
- key sections are present
- provenance is populated
- `document_revision` increments correctly
- published refs are present when status is `canonical_ready`

### Invariant checks

| Invariant | Description |
|-----------|-------------|
| Provenance present | `document.provenance.source_id`, `run_id`, and `corpus_id` are populated |
| Document revisions monotonic | newer canonical publications use higher `document_revision` |
| Sections ordered correctly | section ordinals are monotonically increasing |
| Section/document relations valid | every section references a valid `document_id` |
| Canonical-ready has published refs | `ProcessingManifest` includes exact refs when ready |

### Minimal end-to-end processing path

1. Place a golden bundle in a test storage location
2. Trigger processing
3. Verify `Document`, `Section`, and `ProcessingManifest` rows are written
4. Verify `document.processing_status.updated`, `document.processed`, and `document.withdrawn` behaviors are validated for the relevant lifecycle path
5. Verify lineage is traceable
