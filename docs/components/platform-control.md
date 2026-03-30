# Platform Control

## Purpose

Own source lifecycle and operational control. Platform-control is the entry point for all new data entering Evidara and the control plane for all operational workflows.

## Current state

Initial service scaffolding now exists under `platform-control/`:

- FastAPI app and action-focused routers
- SQLAlchemy models and Alembic migration
- Firecrawl provider and webhook service skeletons
- Configurable local-or-GCS artifact storage adapter
- Configurable noop-or-Pub/Sub raw artifact event publisher
- YAML-backed reference-data seed loader with dry-run support
- Narrow unit and smoke tests for source, run, and webhook flows

Repository scaffolding, component documentation, ADRs, and minimal contracts also exist:

- `contracts/api/platform-control.openapi.yaml`
- `contracts/schemas/raw-artifact-envelope.schema.json`
- `contracts/events/raw-artifact-available.schema.json`

The planned v0 implementation for Firecrawl-backed source setup and preview runs is documented in [../architecture/platform-control-firecrawl-v0-plan.md](../architecture/platform-control-firecrawl-v0-plan.md).

## Source of truth

- Postgres (Cloud SQL) for source metadata, versions, runs, approvals
- GCS for raw artifact storage
- `contracts/api/platform-control.openapi.yaml` for API definition
- `contracts/schemas/raw-artifact-envelope.schema.json` for the raw artifact envelope

## Responsibilities

### Minimal v1

- Jurisdictions and authorities (reference data)
- Seed sources
- Source registry
- Source versions
- Run records
- Approvals
- Raw artifact metadata
- Captured resource inventory for acquired URLs and documents
- Provider job tracking for acquisition backends

### Boundary

- **Does own:** source lifecycle, reference data, runs, approvals, orchestration
- **Does NOT own:** canonical document truth, search projections, document processing

## Minimal next tasks

- [x] Define Postgres entities for sources, versions, runs, approvals
- [x] Define minimal OpenAPI spec (`contracts/api/platform-control.openapi.yaml`)
- [x] Define `RawArtifactEnvelope` schema
- [x] Define `raw_artifact.available` event schema
- [x] Define run lifecycle (states, transitions)
- [x] Define approval states and transitions
- [x] Add provider job and captured resource entities
- [x] Implement Firecrawl provider adapter and webhook handling
- [x] Add YAML-backed seed data loader for jurisdictions, authorities, and extractor profiles
- [ ] Implement Retool source setup, preview review, and approval flow
- [ ] Add AI-assisted draft source setup workflow with human approval gates
- [ ] Document GCP service usage (Cloud Run, Cloud SQL, GCS, Pub/Sub)
- [x] Create initial service scaffolding documentation
- [x] Add preview-run operations runbook

## Minimal v1 Outcome

A user can:

1. Create a source
2. Create a source version
3. Trigger a preview or production run
4. Record raw artifact metadata and captured resources
5. Review preview results
6. Approve a source version

## Later expansion

| Phase | Capability |
|-------|-----------|
| Next | Reference-data editing UI (Retool) |
| Next | Firecrawl-backed preview runs and captured resource inventory |
| Next | AI-assisted source setup in Retool with human approval |
| Next | Drift/repair workflows |
| Later | Research workflow control |
| Later | AI proposal flow (AI proposes, human approves) |
| Later | More granular source family support |

## Dependencies

| Dependency | Purpose |
|-----------|---------|
| Cloud SQL (Postgres) | Source metadata storage |
| GCS | Raw artifact storage |
| Pub/Sub | Event emission (`raw_artifact.available`) |
| Cloud Run | Runtime |
| Firecrawl | Website acquisition for preview and scheduled runs (planned v0) |

## Technology

| Concern | Technology |
|---------|-----------|
| API framework | FastAPI (Python) |
| Runtime | Cloud Run (GCP) |
| Database | Cloud SQL (Postgres) |
| ORM / migrations | SQLAlchemy + Alembic |
| Object Storage | Local filesystem in dev, GCS in cloud environments |
| Events | Noop in local dev, Pub/Sub in cloud environments |
| Reference data seeds | YAML files validated with Pydantic |
| Ops UI | Retool — connects to PostgreSQL (reads) and FastAPI (business actions) |
| Acquisition provider | Firecrawl (planned v0) |
| Operator assistance | Retool Workflows + Agents (planned v0) |

## Key Contracts

- **Produces:** `raw_artifact.available` event
- **API:** `contracts/api/platform-control.openapi.yaml`
- **Schemas:** `RawArtifactEnvelope`
- **Event schema:** `contracts/events/raw-artifact-available.schema.json`

## Testing

See [Platform Control Testing](testing/platform-control-testing.md) for the full testing strategy.

Key tests:

- Unit tests for run and approval state transitions
- Unit tests for Firecrawl request mapping, webhook verification, and idempotency
- Contract tests for `RawArtifactEnvelope`
- Smoke test for one source family lifecycle
- Drift checks: artifact count, content type, empty output detection

## Drift risks

| Risk | Mitigation |
|------|-----------|
| Source format changes silently | Drift checks on artifact count and content type |
| Run state machine becomes inconsistent | Unit tests for all valid/invalid transitions |
| Raw artifact envelope schema diverges from consumers | Contract tests validate schema on every commit |
| Source stops producing artifacts | Artifact count check detects unexpected zeros |
