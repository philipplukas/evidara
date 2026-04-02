# Contracts

## Purpose

Provide the shared language between all Evidara components. Contracts define the explicit, versioned interfaces through which components communicate and evolve independently.

## Current state

Core v1 contract building blocks now exist:

- shared envelope/ref schemas in `contracts/common/`
- control-plane and search OpenAPI specs in `contracts/api/`
- bundle, canonical, and processing schemas in `contracts/schemas/`
- event schemas in `contracts/events/`
- realistic examples in `contracts/examples/`

Implementation code is still evolving, so contracts are the main stabilizing mechanism at this stage.

## Source of truth

- `contracts/` directory is the single source of truth for all interface definitions
- Prose documentation should reference contract files, not duplicate them
- `contracts/README.md` defines naming, versioning, and example conventions
- `contracts/ids/README.md` defines ID families and field-suffix rules

## Structure

```text
contracts/
  api/       # OpenAPI specs for synchronous REST APIs
  common/    # Shared JSON Schema building blocks (event envelopes, refs, provenance)
  events/    # JSON Schemas for async event payloads
  examples/  # Example payloads validated against schemas
  ids/       # ID naming and formatting conventions
  schemas/   # JSON Schemas for shared domain objects and manifests
```

## Standards We Reuse

- JSON Schema Draft 2020-12 for payload validation
- OpenAPI 3.1 for synchronous APIs
- a CloudEvents-aligned envelope for async metadata
- typed `*_ref` objects instead of raw path strings

Contracts intentionally do not try to replace every platform capability. We still rely on:

- Databricks / Unity Catalog lineage for DI-internal table and job lineage
- OpenSearch aliases and versioned physical indices for search cutover and replay
- component-owned operational stores for job execution details that do not need to cross a boundary

## Minimal next tasks

- [x] Define ID conventions (`contracts/ids/README.md`)
- [x] Define `ArtifactBundleManifest` schema
- [x] Define `Document` schema
- [x] Define `Section` schema
- [x] Define `ProcessingManifest` schema
- [x] Define core event schemas
- [x] Define minimal platform-control OpenAPI spec
- [x] Define minimal legal-search OpenAPI spec
- [x] Add automated schema/example validation in CI

The repo's `Docs and Contracts Checks` workflow now acts as the narrow contract-validation gate by validating OpenAPI specs plus JSON schemas and their example payloads.

## Minimal v1 Outcome

All runtime domains can exchange a small, explicit set of payloads:

- `platform-control` publishes immutable bundle handoffs via `artifact_bundle.available`
- `document-intelligence` publishes exact immutable processing results via `document.processed`
- `document-intelligence` reports status back via `document.processing_status.updated`
- `legal-search` builds OpenSearch projections from published DI surfaces, not ad hoc internal tables

## Later expansion

| Phase | Capability |
|-------|-----------|
| Next | `document.withdrawn` consumers in legal-search |
| Next | Projection manifest schema |
| Later | AsyncAPI catalog for events |
| Later | Generated clients from OpenAPI and JSON Schema |
| Later | Consumer-driven compatibility checks |

## Dependencies

| Dependency | Purpose |
|-----------|---------|
| JSON Schema (Draft 2020-12) | Schema definition format |
| OpenAPI 3.1 | API specification format |
| All runtime components | Contracts are consumed across every boundary |

## Governance

- Contract files are the authoritative interface surface.
- Event names stay stable; `event_version` carries major-version changes.
- Additive optional fields are allowed within a version.
- Breaking changes require a new major version and an ADR.
- Contracts should prefer typed refs and manifests over large denormalized payloads.
- Contracts should capture domain ownership and replay semantics, not duplicate every internal platform lifecycle detail.
- Producer and consumer owners must both agree on contract changes.

## Testing

See [Contracts Testing](../../docs/components/testing/contracts-testing.md) for the full testing strategy.

Key tests:

- JSON Schema validity checks
- Example payload validation against schemas
- OpenAPI lint and validation
- Example payloads updated together with schema changes

## Drift risks

| Risk | Mitigation |
|------|-----------|
| Schema changes without example updates | CI validates examples against schemas |
| Breaking changes introduced silently | PR review and ADR requirement |
| Prose docs duplicate and diverge from schemas | Update rules require referencing, not duplicating |
| Downstream consumers couple to internal tables | Published-surface refs are explicit in contracts |
