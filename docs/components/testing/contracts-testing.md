# Contracts Testing

## Scope

Testing strategy for the contracts component, which owns:

- OpenAPI specs (per-component API definitions)
- JSON Schemas (data models: Document, Section, Citation, RawArtifactEnvelope)
- Event schemas (raw_artifact.available, document.processed, index_update.requested)
- ID conventions and ownership rules
- Backwards compatibility of contract changes

---

## Minimal Tests for MVP

### Schema Validity Checks

All schemas must be syntactically valid:

- JSON Schemas parse without errors
- JSON Schemas use correct JSON Schema draft version
- OpenAPI specs parse without errors
- OpenAPI specs conform to the OpenAPI 3.x specification

### Example Payload Validation

Maintain example payloads for core contracts and validate them against schemas:

| Contract | Example Payload | Schema |
|----------|----------------|--------|
| `RawArtifactEnvelope` | `contracts/examples/raw-artifact-envelope.json` | `contracts/schemas/raw-artifact-envelope.schema.json` |
| `Document` | `contracts/examples/document.json` | `contracts/schemas/document.schema.json` |
| `Section` | `contracts/examples/section.json` | `contracts/schemas/section.schema.json` |
| `Citation` | `contracts/examples/citation.json` | `contracts/schemas/citation.schema.json` |
| `raw_artifact.available` | `contracts/examples/raw-artifact-available.json` | `contracts/events/raw-artifact-available.schema.json` |
| `document.processed` | `contracts/examples/document-processed.json` | `contracts/events/document-processed.schema.json` |
| `index_update.requested` | `contracts/examples/index-update-requested.json` | `contracts/events/index-update-requested.schema.json` |

Each example must:

- Parse without errors
- Validate against its schema without violations
- Include all required fields
- Use realistic (not placeholder) values

### OpenAPI Lint / Validation

- Run an OpenAPI linter (e.g., `spectral`, `redocly`) on all OpenAPI specs
- Check for common issues: missing descriptions, undocumented error responses, inconsistent naming

---

## Change Management Guidance

### Contract changes must be explicit

- Every schema change must be a deliberate, reviewed PR
- Do not change schemas as a side effect of implementation work
- Schema changes should be their own commit or PR when possible

### Breaking changes must be called out

- Any change that removes a field, renames a field, changes a type, or tightens a constraint is breaking
- Breaking changes must be flagged in the PR description
- Breaking changes require an ADR (see `docs/adr/`)

### Examples must be updated together with schema changes

- When a schema changes, the corresponding example payload must be updated in the same PR
- CI should validate that examples still pass schema validation
- Stale examples are treated as test failures

### Backwards compatibility rules

- **Additive changes are safe:** adding optional fields, adding new enum values
- **Removal is breaking:** removing fields, removing enum values
- **Type changes are breaking:** changing a field from string to integer
- **New required fields are breaking:** adding a required field to an existing schema

---

## Confidence Goal

These tests should answer:

- **Can components exchange payloads safely?** — Schema validation and example payloads prove that contracts are honored.
- **Can the AI coding tool rely on stable contracts?** — Linting, validation, and change management rules ensure contracts do not silently drift.

---

## What NOT to Overbuild Early

- Do not build automated backwards-compatibility diffing (use manual review for now)
- Do not build contract testing frameworks that test live services against specs (add later as integration tests)
- Do not over-annotate schemas with every possible validation rule — keep schemas as simple as possible while catching real errors

---

## Later Expansion

| Phase | Addition |
|-------|---------|
| Post-MVP | Automated backwards-compatibility checks on PR |
| Post-MVP | Contract testing against running services |
| Later | Schema versioning and migration tooling |
| Later | Consumer-driven contract testing |
