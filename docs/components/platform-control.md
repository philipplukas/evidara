# Platform Control

## Purpose

Own source lifecycle and operational control. Platform-control is the entry point for all new data entering Evidara and the control plane for all operational workflows.

## Current state

Not yet implemented. Repository scaffolding and component documentation exist. Contracts and schemas are planned but not yet defined.

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

### Boundary

- **Does own:** source lifecycle, reference data, runs, approvals, orchestration
- **Does NOT own:** canonical document truth, search projections, document processing

## Minimal next tasks

- [ ] Define Postgres entities for sources, versions, runs, approvals
- [x] Define minimal OpenAPI spec (`contracts/api/platform-control.openapi.yaml`)
- [ ] Define `RawArtifactEnvelope` schema
- [ ] Define run lifecycle (states, transitions)
- [ ] Define approval states and transitions
- [ ] Document GCP service usage (Cloud Run, Cloud SQL, GCS, Pub/Sub)
- [ ] Create initial service scaffolding documentation

## Minimal v1 Outcome

A user can:

1. Create a source
2. Create a source version
3. Trigger a run
4. Record raw artifact metadata
5. Approve a source version

## Later expansion

| Phase | Capability |
|-------|-----------|
| Next | Reference-data editing UI (Retool) |
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

## Technology

| Concern | Technology |
|---------|-----------|
| API framework | FastAPI (Python) |
| Runtime | Cloud Run (GCP) |
| Database | Cloud SQL (Postgres) |
| ORM / migrations | SQLAlchemy + Alembic |
| Object Storage | GCS (for raw artifacts) |
| Events | Pub/Sub |
| Ops UI | Retool — connects to PostgreSQL (reads) and FastAPI (business actions) |

## Key Contracts

- **Produces:** `raw_artifact.available` event
- **API:** `contracts/api/platform-control.openapi.yaml`
- **Schemas:** `RawArtifactEnvelope`

## Testing

See [Platform Control Testing](testing/platform-control-testing.md) for the full testing strategy.

Key tests:

- Unit tests for run and approval state transitions
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
