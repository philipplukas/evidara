# Contracts Testing

## Scope

Testing strategy for the contracts component, which owns:

- OpenAPI specs
- shared JSON Schema building blocks
- manifest and canonical schemas
- event schemas
- ID conventions and naming rules
- backwards compatibility guidance

## Minimal Tests for MVP

### Schema validity checks

All schemas must be syntactically valid:

- JSON Schemas parse without errors
- JSON Schemas use Draft 2020-12
- OpenAPI specs parse without errors
- OpenAPI specs conform to OpenAPI 3.1

### Example payload validation

Maintain example payloads for core contracts and validate them against schemas:

| Contract | Example Payload | Schema |
|----------|----------------|--------|
| `ArtifactBundleManifest` | `contracts/examples/artifact-bundle-manifest.json` | `contracts/schemas/artifact-bundle-manifest.schema.json` |
| `ProcessingManifest` | `contracts/examples/processing-manifest.json` | `contracts/schemas/processing-manifest.schema.json` |
| `Document` | `contracts/examples/document.json` | `contracts/schemas/document.schema.json` |
| `Section` | `contracts/examples/section.json` | `contracts/schemas/section.schema.json` |
| `Citation` | `contracts/examples/citation.json` | `contracts/schemas/citation.schema.json` |
| `artifact_bundle.available` | `contracts/examples/artifact-bundle-available.json` | `contracts/events/artifact-bundle-available.schema.json` |
| `document.processing_status.updated` | `contracts/examples/document-processing-status-updated.json` | `contracts/events/document-processing-status-updated.schema.json` |
| `document.processed` | `contracts/examples/document-processed.json` | `contracts/events/document-processed.schema.json` |
| `document.withdrawn` | `contracts/examples/document-withdrawn.json` | `contracts/events/document-withdrawn.schema.json` |
| `index_update.requested` | `contracts/examples/index-update-requested.json` | `contracts/events/index-update-requested.schema.json` |

Each example must:

- validate successfully
- include all required fields
- use realistic values

### OpenAPI validation

- Run OpenAPI validation on all OpenAPI specs
- Check for common issues like missing descriptions and undocumented error responses

### CI enforcement

The `.github/workflows/docs-and-contracts.yml` workflow is the contract-validation gate. It must fail if:

- a schema is syntactically invalid
- an example payload no longer matches its schema
- a required example payload file is missing
- an OpenAPI spec fails validation

## Change Management Guidance

- Every contract change must be explicit and reviewed.
- Breaking changes require an ADR.
- Additive optional fields are preferred.
- Examples must be updated together with schema changes.

## Confidence Goal

These tests should answer:

- **Can components exchange payloads safely?**
- **Can consumers rely on stable naming, versioning, and provenance rules?**

## What NOT to Overbuild Early

- Do not build live service contract tests yet
- Do not build automated compatibility diff tooling before the contracts stabilize
- Do not over-constrain schemas with speculative rules