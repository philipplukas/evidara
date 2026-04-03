# Platform Control

## Purpose

Own source lifecycle and operational control. Platform-control is the entry point for all new data entering Evidara and the control plane for acquisition, governance, approval, and scope metadata.

## Current state

Platform-control now has a running FastAPI service with persisted entities and migration-backed schemas for source lifecycle, runs, webhook receipts, raw artifacts, bundle manifests, and DI status/lifecycle event consumption. Core API endpoints are implemented for reference data, sources, versions, runs, preview-summary review, Firecrawl callbacks, and DI event ingest (`document.processing_status.updated`, `document.processed`, `document.withdrawn`) with run-scoped read surfaces.

For the current slice, scope fields such as `tenant_id`, `corpus_id`, and `scope_type` are frozen through source-version acquisition config and copied into bundle/event provenance. First-class corpus CRUD is still follow-on work.

Repo-owned Retool control-panel artifacts now live under `platform-control/retool/`, including the
control-panel manifest, direct-Postgres queries, preview workflow, and Source Setup Copilot prompt.

See [Platform Control Implementation Plan](platform-control-implementation-plan.md) for the planned repo structure, worker layout, and phased delivery approach.

## Source of truth

- Postgres (Cloud SQL) for sources, versions, runs, approvals, and reference data
- GCS for raw artifacts and immutable artifact bundle manifest objects
- `contracts/api/platform-control.openapi.yaml` for API definition
- `contracts/schemas/artifact-bundle-manifest.schema.json` for immutable DI handoff manifests

## Responsibilities

### Minimal v1

- Scope metadata (`tenant_id`, `corpus_id`, `scope_type`) frozen for the run and handoff path
- Jurisdictions and authorities (reference data)
- Source registry
- Source versions as frozen governed acquisition config
- Run records and acquisition checkpoints
- Source snapshots, artifact registration, and bundle manifests

Bundle manifests should be published as immutable JSON objects. If platform-control needs to query them operationally, it should mirror searchable fields into its own query surfaces rather than relying on path parsing conventions.

### Boundary

- **Does own:** source lifecycle, scope governance, reference data, runs, approvals, connector execution, provenance registration
- **Does NOT own:** canonical document truth, search projections, parsing, canonical resolution

## Minimal next tasks

- [x] Define Postgres entities for sources, versions, runs, provider jobs, artifacts, and DI event tracking
- [x] Define OpenAPI spec (`contracts/api/platform-control.openapi.yaml`)
- [x] Define `ArtifactBundleManifest` schema
- [x] Create the initial `platform-control/` API scaffold
- [ ] Create the connector-worker scaffold under `platform-control/`
- [~] Define run lifecycle and replay modes
- [x] Define approval states and transitions
- [~] Define reference snapshot export mechanics for DI
- [ ] Document GCP service usage (Cloud Run, Cloud SQL, GCS, Pub/Sub)

## Minimal v1 Outcome

A user can:

1. Create a source and freeze scope metadata for the run path
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
- **Consumes:** `document.processing_status.updated`, `document.processed`, `document.withdrawn`
- **API:** `contracts/api/platform-control.openapi.yaml`
- **Schemas:** `ArtifactBundleManifest`

## Developer workflow

- Service check: `bash scripts/check-platform-control.sh`
- Docs/contracts checks: `bash scripts/check_docs.sh`
- Legal-search checks (cross-component CI parity): `bash scripts/check-legal-search.sh`

## Testing

See [Platform Control Testing](testing/platform-control-testing.md) for the full testing strategy.

Key tests:

- Unit tests for run and approval state transitions
- Unit tests for reference-data management and Firecrawl request mapping
- Contract tests for `ArtifactBundleManifest`
- Contract tests for `artifact_bundle.available`
- Contract tests for consumed `document.processing_status.updated` values, including invalid-status handling
- Smoke tests for health, preview success, preview summary, and failed preview handling
- Integration test for Postgres webhook-dedupe behavior

## Drift risks

| Risk | Mitigation |
|------|-----------|
| Source format changes silently | Artifact count and content-type drift checks |
| Run state becomes inconsistent | Unit tests for valid and invalid transitions |
| Bundle manifests drift from DI expectations | Schema validation and example payload tests |
| Scope metadata changes accidentally | Source-version governance, manifest provenance, and audit trail |
