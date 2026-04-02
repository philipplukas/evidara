# Platform Control

## Purpose

Own source lifecycle and operational control. Platform-control is the entry point for all new data entering Evidara and the control plane for tenant, corpus, acquisition, and approval workflows.

## Current state

Contracts and API shape are defined, but the service itself is not yet implemented. Repository scaffolding and component documentation exist, yet the runtime service, worker processes, and database schema are not built yet.

See [Platform Control Implementation Plan](platform-control-implementation-plan.md) for the planned repo structure, worker layout, and phased delivery approach.

## Source of truth

- Postgres (Cloud SQL) for sources, corpora, versions, runs, approvals, and reference data
- GCS for raw artifacts and immutable artifact bundle manifest objects
- `contracts/api/platform-control.openapi.yaml` for API definition
- `contracts/schemas/artifact-bundle-manifest.schema.json` for immutable DI handoff manifests

## Responsibilities

### Minimal v1

- Tenants and corpora
- Jurisdictions and authorities (reference data)
- Source registry
- Source versions as frozen governed acquisition config
- Run records and acquisition checkpoints
- Source snapshots, artifact registration, and bundle manifests

Bundle manifests should be published as immutable JSON objects. If platform-control needs to query them operationally, it should mirror searchable fields into its own query surfaces rather than relying on path parsing conventions.

### Boundary

- **Does own:** source lifecycle, corpora, reference data, runs, approvals, connector execution, provenance registration
- **Does NOT own:** canonical document truth, search projections, parsing, canonical resolution

## Minimal next tasks

- [ ] Define Postgres entities for sources, corpora, versions, runs, and approvals
- [x] Define OpenAPI spec (`contracts/api/platform-control.openapi.yaml`)
- [x] Define `ArtifactBundleManifest` schema
- [ ] Create the initial `platform-control/` API scaffold
- [ ] Create the connector-worker scaffold under `platform-control/`
- [ ] Define run lifecycle and replay modes
- [ ] Define approval states and transitions
- [ ] Define reference snapshot export mechanics for DI
- [ ] Document GCP service usage (Cloud Run, Cloud SQL, GCS, Pub/Sub)

## Minimal v1 Outcome

A user can:

1. Create a source in a corpus
2. Create and approve a source version
3. Trigger a run with replay/backfill scope
4. Register a source snapshot and one or more artifacts
5. Publish an immutable bundle manifest and emit `artifact_bundle.available`

## Later expansion

| Phase | Capability |
|-------|-----------|
| Next | Reference-data editing UI |
| Next | Drift and repair workflows |
| Later | AI-generated draft source versions |
| Later | More granular source family support |

## Dependencies

| Dependency | Purpose |
|-----------|---------|
| Cloud SQL (Postgres) | Control-plane metadata |
| GCS | Raw artifacts and bundle manifests |
| Pub/Sub | Event emission and status consumption |
| Cloud Run | Runtime |

## Platform Capabilities We Reuse

- Pub/Sub for event transport
- CloudEvents-aligned event metadata through the shared contract envelope
- GCS object immutability patterns for durable raw artifacts and manifest storage

Lineage and document semantics that cross boundaries still remain Evidara-owned contracts.

## Key Contracts

- **Produces:** `artifact_bundle.available`
- **Consumes:** `document.processing_status.updated`
- **API:** `contracts/api/platform-control.openapi.yaml`
- **Schemas:** `ArtifactBundleManifest`

## Testing

See [Platform Control Testing](testing/platform-control-testing.md) for the full testing strategy.

Key tests:

- Unit tests for run and approval state transitions
- Contract tests for `ArtifactBundleManifest`
- Contract tests for `artifact_bundle.available`
- Contract tests for consumed `document.processing_status.updated` values, including invalid-status handling
- Smoke test for one source family lifecycle

## Drift risks

| Risk | Mitigation |
|------|-----------|
| Source format changes silently | Artifact count and content-type drift checks |
| Run state becomes inconsistent | Unit tests for valid and invalid transitions |
| Bundle manifests drift from DI expectations | Schema validation and example payload tests |
| Corpus assignment changes accidentally | Source/version approval workflow and audit trail |
