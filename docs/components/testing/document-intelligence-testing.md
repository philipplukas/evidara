# Document Intelligence Testing

## Scope

Testing strategy for the document-intelligence component, which owns:

- Raw artifact ingestion
- Parsing (HTML, PDF, etc.)
- Segmentation (splitting into sections)
- Canonical document creation
- Section creation and ordering
- Citation extraction
- Jurisdiction assignment
- Quality checks

---

## Minimal Tests for MVP

### Unit Tests

#### Parsing helpers

- HTML tag stripping / normalization
- Section title extraction from headings
- Citation pattern matching (e.g., "Art. 123 OR", "§ 42 BGB")
- Content type detection

#### Section construction logic

- Sections are created in correct order
- Section parent-child relationships are valid
- Empty sections are handled (skipped or flagged)

### Schema Validation

- `Document` output conforms to JSON Schema
- `Section` output conforms to JSON Schema
- `Citation` output conforms to JSON Schema
- `document.processed` event payload conforms to event schema

### Golden Document Tests

Use 10–20 representative documents from `tests/golden/`.

For each golden document, assert:

- Document is created (not null, not empty)
- Document type is correct
- Section count is within expected range
- Key sections are present (by title or position)
- Citation count is within expected range
- Jurisdiction is correctly assigned
- Lineage fields are populated (`source_id`, `run_id`, `artifact_id`)
- Required fields are non-null (`title`, `jurisdiction`, `document_type`)

See [Golden Datasets](../../testing/golden-datasets.md) for sample selection and storage.

### Invariant Checks

These must hold for every processed document, regardless of input:

| Invariant | Description |
|-----------|-------------|
| Lineage present | `document.source_id`, `document.run_id`, `document.artifact_id` are not null |
| Sections ordered correctly | Section sequence numbers are monotonically increasing |
| Required fields present | `title`, `jurisdiction`, `document_type` are populated |
| Section/document relations valid | Every section references a valid `document_id` |
| No orphaned sections | Every section belongs to exactly one document |

### Minimal End-to-End Processing Path

One test that takes a raw artifact from object storage and produces a canonical document in Delta:

1. Place a golden input in a test storage location
2. Trigger processing
3. Verify a Document, Sections, and Citations are written
4. Verify a `document.processed` event is emitted
5. Verify lineage is traceable

---

## Drift Checks

| Check | What it catches |
|-------|----------------|
| Average section count changes sharply | Source format changed or parser broke |
| Citation count changes sharply | Citation extraction logic regressed |
| Title/jurisdiction null rate spikes | Metadata extraction degraded |
| Expected headings/citations disappear in golden docs | Parser no longer handles known patterns |

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
| Post-MVP | Expanded golden set (per source family) |
| Post-MVP | Processing performance benchmarks |
| Later | Property-based tests for parser edge cases |
| Later | Quality scoring with threshold alerts |
| Later | Full distribution monitoring for semantic drift |
