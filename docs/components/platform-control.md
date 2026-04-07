# Platform Control

## Purpose

Own source lifecycle and operational control. Platform-control is the entry point for all new data entering Evidara and the control plane for acquisition, governance, approval, and scope metadata.

## Current state

Platform-control now has a running FastAPI service with persisted entities and migration-backed schemas for source lifecycle, runs, webhook receipts, raw artifacts, bundle manifests, and DI status/lifecycle event consumption. Core API endpoints are implemented for sources, versions, runs, Firecrawl callbacks, and DI event ingest (`document.processing_status.updated`, `document.processed`, `document.withdrawn`) with run-scoped read surfaces.

For the current slice, scope fields such as `tenant_id`, `corpus_id`, and `scope_type` are frozen through source-version acquisition config and copied into bundle/event provenance. Run creation now also accepts explicit `scope` and `replay` metadata so partial reruns and backfills can be recorded on the control-plane side even though resumable frontier orchestration is still follow-on work. First-class corpus CRUD is still follow-on work.

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
- [x] Create the connector-worker scaffold under `platform-control/`
- [~] Define run lifecycle and replay modes
  Current API support exists for `scope` and `replay` metadata on run creation, but resumable checkpoints/frontier orchestration are not implemented yet.
- [x] Define approval states and transitions
- [x] Define reference snapshot export mechanics for DI
- [x] Document GCP service usage (Cloud Run, Cloud SQL, GCS, Pub/Sub)

Replay/checkpoint constraint: checkpoint/frontier state is not yet persisted as a first-class model. Operators should treat replay as run-scoped metadata plus provider-side reruns until dedicated checkpoint orchestration lands.

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

## Authentication

When any of `PLATFORM_CONTROL_API_KEY`, `PLATFORM_CONTROL_OPERATOR_API_KEY`, or
`PLATFORM_CONTROL_SERVICE_API_KEY` is set, matching routes require `X-API-Key`.
Unset keys keep local development open. Legacy single-key mode is
`PLATFORM_CONTROL_API_KEY` only; scoped operator vs service keys are documented in
[ADR-0020](../adr/adr-0020-api-authentication.md).

## Developer workflow

- Service check: `bash scripts/check-platform-control.sh`
- Docs/contracts checks: `bash scripts/check_docs.sh`
- Legal-search checks (cross-component CI parity): `bash scripts/check-legal-search.sh`

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
| Scope metadata changes accidentally | Source-version governance, manifest provenance, and audit trail |
