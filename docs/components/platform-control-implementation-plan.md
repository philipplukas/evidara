# Platform Control Implementation Plan

## Status

Partially superseded. This document still captures useful ownership and sequencing notes for `platform-control`, but its earlier TypeScript/NestJS API-service shape is no longer the current implementation direction.

## Purpose

Provide a concrete structure plan for building `platform-control` as the operational control plane for Evidara while keeping connector ownership, run orchestration, source snapshots, artifact registration, and bundle-manifest publication inside the same top-level component boundary.

## Current state

`platform-control` now has a running FastAPI service, Alembic migrations, SQLAlchemy models, source/version/run APIs, Firecrawl webhook handling, raw artifact persistence, bundle-manifest publication, `artifact_bundle.available` emission, and DI status/lifecycle event ingest. Tests exist for core service, webhook, publication, and smoke-path behavior.

Important: the repo has since standardized the control-plane API on Python/FastAPI. Treat [`docs/components/platform-control.md`](platform-control.md) and the code under [`platform-control/`](../../platform-control/) as authoritative for current runtime and language choices. The TypeScript-specific structure sketches later in this document are preserved as historical planning notes and should not be used as implementation guidance for new work.

## Goal

Deliver a minimal `platform-control` component that can:

1. Define sources and source versions
2. Trigger and track runs
3. Register source snapshots and artifacts with provenance
4. Own connector configuration and execution metadata
5. Publish immutable artifact bundle manifests and emit `artifact_bundle.available`
6. Receive processing feedback from downstream systems

The next implementation phase should establish a cleaner separation between the current FastAPI control-plane service and any future connector-worker runtime without splitting them into separate top-level components.

## Planning assumptions

- `platform-control` owns source lifecycle, runs, approvals, reference data, connector configuration, source snapshots, artifact registration, and bundle-manifest publication.
- Connector execution belongs to `platform-control`, even if connectors run in separate deployment units.
- `document-intelligence` starts at the artifact-bundle boundary and should not fetch upstream sources directly.
- `contracts/` remains the highest-authority location for public API and event definitions.
- Internal code structures may be stricter than the current contracts, but some contract-edge adapters should remain tolerant until the final hardening pass.
- The MVP should support one connector family cleanly before the component expands to many protocols.

## Source of truth

- Postgres for operational entities such as sources, corpora, source versions, runs, approvals, source snapshots, and artifact metadata
- GCS for raw artifact and immutable bundle-manifest storage
- `contracts/api/platform-control.openapi.yaml` for public control-plane API shape
- `contracts/schemas/artifact-bundle-manifest.schema.json` for immutable DI handoff shape
- This plan for intended future-state repo structure and implementation sequencing

## Minimal next tasks

- [x] Create the `platform-control/` API scaffold
- [x] Create the connector-worker scaffold under the same top-level component (`connector_worker` entrypoint, `Dockerfile.worker`)
- [x] Define initial Postgres tables and migrations for sources, source versions, runs, raw artifacts, webhook receipts, DI event tracking, and reference data
- [x] Implement the first source/version/run/artifact APIs
- [x] Implement bundle-manifest creation and `artifact_bundle.available` emission
- [x] Implement one connector path with one source family; Firecrawl acquisition is dispatched from the connector worker when `PLATFORM_CONTROL_RUN_DISPATCH_BACKEND=worker` on the API (webhook ingress stays on the API service)
- [x] Add tests for run state, artifact registration, webhook handling, and event publication flow

## Target architecture

## Runtime split

`platform-control` should be one component with two implementation sub-parts:

- a TypeScript API service
- Python connector workers

This is one ownership boundary, not two separate products.

### API service responsibilities

- expose control-plane APIs
- persist control-plane state in Postgres
- orchestrate runs
- register source snapshots and artifacts
- publish bundle manifests
- emit events
- receive processing-status feedback

### Worker responsibilities

- execute connector runs
- fetch upstream content
- preserve raw upstream payloads
- write artifacts to GCS
- report artifact metadata and execution status back to the API or shared persistence layer

## Recommended repo structure

The recommended MVP structure is:

```text
platform-control/
  README.md
  package.json
  tsconfig.json
  biome.json
  nest-cli.json
  src/
    main.ts
    app.module.ts
    config/
    infrastructure/
      db/
      storage/
      events/
      auth/
      observability/
    modules/
      health/
      sources/
      source_versions/
      runs/
      approvals/
      artifacts/
      reference_data/
      connector_runs/
      processing_feedback/
    shared/
      ids/
      time/
      errors/
      pagination/
      state/
  test/
    unit/
    integration/
    fixtures/
  db/
    migrations/
    seeds/
    queries/
  workers/
    README.md
    pyproject.toml
    src/platform_control_workers/
      cli/
      config/
      connectors/
        base.py
        registry.py
        rest_api/
        http_scrape/
        sharepoint/
        google_drive/
        huggingface/
      acquisition/
        fetch/
        storage/
        manifests/
        dedupe/
      platform_control/
        models.py
        api_client.py
        artifact_registration.py
        run_status.py
      jobs/
        execute_run.py
        requeue_run.py
      shared/
        ids.py
        time.py
        logging.py
    tests/
      unit/
      smoke/
      fixtures/
  docs/
    README.md
```

This keeps:

- one top-level component boundary
- one TypeScript subproject for the API
- one Python subproject for workers
- one place for database migrations

## Why this structure

- the API and workers evolve independently but remain under one ownership boundary
- the worker runtime can use Python libraries without polluting the Node.js service
- the API stays focused on control-plane workflows
- per-connector code is isolated under `workers/src/platform_control_workers/connectors/`
- database assets stay visible to both the API and the team

## What not to do

- do not create a second top-level `ingestion/` or `connectors/` component in MVP
- do not scatter connector code across unrelated folders
- do not place connector logic inside the API request handlers
- do not let workers write directly into downstream component storage

## API service structure

## Module layout

The TypeScript service should use a module-per-domain pattern under `src/modules/`.

Recommended modules:

- `sources`
- `source_versions`
- `runs`
- `approvals`
- `artifacts`
- `reference_data`
- `connector_runs`
- `processing_feedback`
- `health`

Within each module, keep a predictable structure:

```text
sources/
  sources.module.ts
  sources.controller.ts
  sources.service.ts
  sources.repository.ts
  sources.schemas.ts
  sources.types.ts
  sources.mapper.ts
```

Not every module needs every file on day one, but the structure should stay predictable.

## Shared and infrastructure layers

Use:

- `src/shared/` for small reusable primitives only
- `src/infrastructure/` for adapters to Postgres, GCS, Pub/Sub, auth, config, and observability

Do not place domain logic in `infrastructure/`.

## Database plan

Keep database assets under `platform-control/db/`:

- `migrations/` for schema migrations
- `seeds/` for bootstrap development/reference data
- `queries/` for operational SQL that should remain explicit

Recommended operational tables:

- `sources`
- `source_versions`
- `runs`
- `artifacts`
- `source_snapshots`
- `approvals`
- `jurisdictions`
- `authorities`
- later `run_events` or `run_status_history`

Keep the Postgres model normalized. This is control-plane data, not analytical serving data.

## Worker structure

## Worker philosophy

Start with one generic connector-runner package, not one standalone app per connector.

That means:

- one Python worker project
- one connector registry
- multiple connector implementations inside that registry
- one main execution entrypoint that dispatches by connector type

This avoids an explosion of tiny worker services in MVP.

## Worker package layout

### `connectors/`

Contains connector-family implementations.

Recommended pattern:

- `base.py`
- `registry.py`
- one folder per connector family

Each connector family folder should contain:

- config parsing
- upstream fetch logic
- response normalization
- artifact manifest construction

### `acquisition/`

Contains worker-side mechanics shared across connector types:

- HTTP/client wrappers
- object-storage writers
- checksum/deduplication helpers
- manifest builders

### `platform_control/`

Contains the worker’s integration with the control-plane service:

- run fetch or run bootstrap client
- artifact registration client
- run heartbeat/status updates
- typed worker-side models

### `jobs/`

Contains entrypoints for deployment and execution:

- `execute_run.py`
- `requeue_run.py`

The default entrypoint should take a run identifier and execute one connector run deterministically.

## Connector-family guidance

Start with a small family-based structure, not a source-per-folder structure.

Recommended initial connector families:

- `rest_api/`
- `http_scrape/`

Planned additional families:

- `sharepoint/`
- `google_drive/`
- `huggingface/`

This gives room for reuse across many sources that use the same acquisition pattern.

## Deployment units

## API deployment

- one Cloud Run service for the NestJS API

## Worker deployment

Start with one Python worker image and multiple execution modes if needed.

Recommended MVP deployment shape:

- one connector worker container image
- one or more Cloud Run jobs using that same image with different commands or arguments

This keeps build/deploy complexity low while preserving flexibility.

Do not create one container image per connector in MVP unless operational evidence demands it.

## Interaction pattern

## Happy-path flow

1. API creates or receives a run trigger
2. API records the run in Postgres
3. Worker receives the run context
4. Worker loads connector configuration for the source version
5. Worker fetches upstream content
6. Worker writes raw artifact(s) to GCS
7. Worker calls back into the API or shared registration path to register the source snapshot, artifact metadata, and provenance
8. API persists snapshot/artifact lineage and writes an immutable bundle manifest
9. API emits `artifact_bundle.available`
10. Downstream processing begins

## Feedback path

`platform-control` should also expose a minimal path for downstream processing feedback so the run record can reflect:

- accepted
- processing
- canonical_ready
- failed
- withdrawn
- skipped_duplicate

This can begin as a small internal API or internal event consumer and be hardened later.

## Testing

See [Platform Control Testing](testing/platform-control-testing.md) for the component testing strategy. The implementation should adopt the following structure.

### API tests

Under `platform-control/test/`:

- `unit/` for services, validators, and state machines
- `integration/` for API plus Postgres behavior
- `fixtures/` for request and model fixtures

### Worker tests

Under `platform-control/workers/tests/`:

- `unit/` for connector logic and artifact-manifest building
- `smoke/` for end-to-end worker execution against fixtures
- `fixtures/` for connector payload samples

### Cross-boundary tests

Add a small number of tests that verify:

- run creation to worker execution handoff
- artifact registration correctness
- bundle-manifest correctness
- `artifact_bundle.available` emission
- failure recording when acquisition breaks

## Documentation

Implementation should ship with:

- `platform-control/README.md` for local development and component overview
- `platform-control/workers/README.md` for connector-worker conventions
- updates to `docs/components/platform-control.md`
- runbooks once scheduling, replay, or operational repair procedures are stable enough to verify

## Phased delivery plan

## Phase 0: Component scaffold

Create:

- TypeScript service scaffold
- Python worker scaffold
- database migration folder
- initial READMEs

## Phase 1: Core control-plane API

> **Contract-first gate:** Before implementing new API modules (`artifacts`, `connector_runs`, `processing_feedback`), their paths and schemas must be added to `contracts/api/platform-control.openapi.yaml` first. Implementation follows the contract, not the other way around. This ensures the downstream `document-intelligence` contract boundary remains stable.

Implement:

- `sources`
- `source_versions`
- `runs`
- `source_snapshots`
- `artifacts`
- `reference_data`

## Phase 2: First worker path

Implement:

- generic connector runner
- one connector family
- raw artifact write plus bundle-manifest registration flow

## Phase 3: Evented handoff

Implement:

- `artifact_bundle.available`
- downstream processing-status feedback
- improved run lifecycle visibility

## Phase 4: Hardening

Implement:

- retries and replay support
- more connector families
- stronger observability
- scheduling and repair workflows

## Dependencies

| Dependency | Purpose |
|-----------|---------|
| Node.js and TypeScript | API service implementation |
| NestJS | Control-plane application framework |
| Postgres | Operational system of record |
| Cloud Run | API runtime |
| Python | Connector-worker implementation |
| GCS | Raw artifact and bundle-manifest storage |
| Pub/Sub | Pipeline progression events |
| Terraform | Infrastructure provisioning |
| GitHub Actions | CI/CD orchestration |

## Later expansion

| Phase | Capability |
|-------|-----------|
| Next | richer connector families and source snapshots |
| Next | internal admin workflows and repair actions |
| Later | scheduling UI and reference-data editing UI |
| Later | richer run-event history and source health views |
| Later | more granular worker deployment strategies |

## Drift risks

| Risk | Mitigation |
|------|-----------|
| connector logic leaks into API handlers | keep acquisition only in `workers/` and treat the API as orchestration plus persistence |
| one source gets a bespoke structure that breaks reuse | organize workers by connector family, not source name |
| worker and API models drift silently | keep shared public contracts in `contracts/` and add integration tests at the registration boundary |
| too many deployment units appear too early | start with one API service and one worker image |
| database logic spreads into random services | keep explicit migrations and repositories under predictable folders |
