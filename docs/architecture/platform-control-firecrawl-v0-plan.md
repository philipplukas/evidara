# Platform-Control Firecrawl V0 Plan

## Status

Planned

## Purpose

Translate the current platform-control design into an execution-ready plan for a 1-3 person infra/data engineering team. The goal is a small but durable v0 that lets operators define sources, run Firecrawl previews, review results, and prepare for a later source-specific extractor without reworking the control plane.

## Goals

- Keep `platform-control` as the system of record for sources, versions, runs, approvals, and raw artifact lineage.
- Use Retool for the internal operator workflow and AI-assisted setup experience.
- Use Firecrawl as an acquisition provider behind a provider adapter, not as a first-class domain model.
- Preserve enough raw and normalized capture data for a later exhaustive extractor to replay or reprocess old runs.

## Non-goals

- Custom admin frontend outside Retool
- Fully automated approvals
- General-purpose agent orchestration platform
- Exhaustive extraction logic for every source family
- Live Firecrawl calls in CI

## Target Operator Flow

1. Add or edit `jurisdiction` and `authority` reference data.
2. Create a `source` with business identity only.
3. Create a draft `source_version` with:
   - acquisition spec
   - linked extractor profile
   - preview limits
4. Trigger a preview run.
5. Review captured resources and raw artifact summary in Retool.
6. Edit acquisition settings if needed.
7. Approve or reject the version.
8. Trigger production runs from approved versions only.

## V0 Architecture

### Durable control-plane entities

- `jurisdictions`
- `authorities`
- `sources`
- `source_versions`
- `runs`
- `provider_jobs`
- `raw_artifacts`
- `captured_resources`
- `extractor_profiles`
- `webhook_receipts`

### Separation of concerns

- `source` stores business identity and ownership.
- `source_version` stores a specific acquisition configuration snapshot.
- `extractor_profile` stores later extraction intent and source-family-specific rules.
- `run` stores lifecycle and summary status.
- `provider_jobs` stores Firecrawl-specific execution metadata.
- `raw_artifacts` stores durable handoff metadata for downstream processing.
- `captured_resources` stores normalized, provider-neutral inventory for fetched URLs and documents.

### Initial service/API shape

- `POST /v1/sources`
- `POST /v1/sources/{id}/versions`
- `POST /v1/versions/{id}/approve`
- `POST /v1/versions/{id}/reject`
- `POST /v1/runs`
- `GET /v1/runs/{id}`
- `POST /v1/firecrawl/webhooks`

Retool reads list views directly from Postgres and uses the API only for business actions and webhooks.

## Workstreams

### Workstream 1: Schema and service scaffold

- Add initial Alembic migration for the control-plane tables.
- Add SQLAlchemy models and Pydantic schemas.
- Implement source, source-version, approval, and run services.
- Implement run and approval state machines.

### Workstream 2: Firecrawl acquisition path

- Add a provider interface with a Firecrawl implementation.
- Create Firecrawl preview and production run request mapping.
- Store provider job IDs and request snapshots.
- Verify webhook signatures and persist raw webhook payloads.
- Write raw artifacts to GCS and normalized rows to `captured_resources`.
- Emit `raw_artifact.available` for durable downstream processing.

### Workstream 3: Retool operator workflow

- Build `Reference Data`, `Sources`, `Draft Version`, `Preview Review`, and `Runs` pages.
- Use direct Postgres queries for browse/filter/list screens.
- Use platform-control API calls for approve/reject/run actions.
- Add a preview summary table showing:
  - captured URL count
  - content-type breakdown
  - PDFs discovered
  - likely decision pages
  - likely boilerplate or duplicate pages

### Workstream 4: AI-assisted setup

- Add a Retool workflow `run_firecrawl_preview`.
- Add a Retool agent `Source Setup Copilot`.
- Limit agent tools to structured actions:
  - list jurisdictions and authorities
  - create draft source
  - save acquisition spec
  - trigger preview
  - summarize preview
  - propose include/exclude rules
- Keep human approval mandatory before production use.

## Backlog

| ID | Task | Output | Suggested owner |
|----|------|--------|-----------------|
| PC-001 | Create Alembic migration for core tables | Initial schema in `platform-control` | API/data |
| PC-002 | Add SQLAlchemy models | Models for source/version/run/artifact entities | API/data |
| PC-003 | Add Pydantic schemas and settings | Request/response DTOs and validated config | API |
| PC-004 | Implement source and version actions | Create source and create version endpoints | API |
| PC-005 | Implement approval state machine | Approve/reject actions with validation | API |
| PC-006 | Implement run state machine | Create run and get run status endpoints | API |
| PC-007 | Add Firecrawl provider adapter | Preview and production request mapping | Data |
| PC-008 | Add provider job persistence | `provider_jobs` table and service | API/data |
| PC-009 | Add webhook signature verification and dedupe | Verified webhook receipts with idempotency | API |
| PC-010 | Add artifact store and GCS write path | Raw Firecrawl payloads stored in object storage | Data |
| PC-011 | Add captured-resource normalization | Provider-neutral fetched resource inventory | Data |
| PC-012 | Emit `raw_artifact.available` | Pub/Sub event emission from stored artifacts | API/data |
| PC-013 | Build Retool read views | Reference data, sources, versions, runs tables | Ops |
| PC-014 | Build Retool action screens | Draft, approve, reject, preview, rerun flows | Ops |
| PC-015 | Build preview summary screen | Captured-resource review and operator feedback loop | Ops |
| PC-016 | Add Retool preview workflow | Firecrawl preview orchestration | Ops |
| PC-017 | Add Retool setup agent | AI-assisted source setup and preview guidance | Ops |
| PC-018 | Add unit, contract, and smoke tests | MVP confidence gates | API/data |
| PC-019 | Add operational docs and runbook | Preview procedure and recovery steps | Whole team |

## Milestones

### Milestone 1: Control plane boots

Done when:

- Sources, versions, approvals, and runs persist correctly.
- State transitions reject invalid moves.
- `POST /v1/runs` can create a run without yet calling Firecrawl.

### Milestone 2: Preview ingestion works

Done when:

- A preview run creates a Firecrawl job record.
- Webhooks are verified and idempotent.
- Raw artifacts and captured resources are persisted.
- A run reaches `completed` or `failed` with summary counts.

### Milestone 3: Operator flow is usable

Done when:

- Retool supports create -> preview -> review -> approve.
- The setup agent can propose a draft acquisition spec from a seed URL.
- Human approval remains the final gate before production runs.

## Testing Plan

### Unit tests

- Run state transitions
- Approval state transitions
- Acquisition-spec validation
- Firecrawl request mapping
- Webhook signature verification
- Webhook idempotency and dedupe behavior

### Contract tests

- `RawArtifactEnvelope` schema validation
- `raw_artifact.available` event validation
- Example webhook payload mapping to internal models

### Smoke tests

- Create source -> create version -> approve -> preview run -> artifact recorded
- Health endpoint returns `200`
- Failed preview run is surfaced in run status and not left silent

### Drift checks

- Artifact count not zero
- Content type is within expected set
- Empty output is detected
- Captured-resource count does not collapse unexpectedly

### CI guidance

- Stub Firecrawl at the provider boundary in CI.
- Use fixture payloads for webhook tests.
- Do not depend on live Firecrawl, live Retool, or live GCS in the default CI path.

## Documentation Plan

Update these docs in the same PRs as implementation:

- `docs/components/platform-control.md`
- `docs/components/testing/platform-control-testing.md`
- `docs/runbooks/firecrawl-preview-run.md`
- `contracts/api/platform-control.openapi.yaml` when API actions change
- `docs/architecture/boundary-contracts.md` only if boundary payloads change

## Recommended Team Split

### One person

- Build the API, schema, and webhook path first.
- Add Firecrawl capture next.
- Add Retool screens and agent last.

### Two people

- Person 1: schema, API, state machines, webhook handling
- Person 2: Retool screens, workflow, agent, preview review UX

### Three people

- Person 1: schema, models, and API
- Person 2: Firecrawl integration, GCS storage, event emission
- Person 3: Retool app, workflow, and AI setup assistant

## Out of Scope for V0

- Full CRUD APIs for every entity
- Automatic approval decisions
- Production alerting beyond basic smoke and drift checks
- Generic extractor orchestration for all source families
- Rich analytics for crawl quality

## Exit Criteria

V0 is complete when an operator can define a source, generate a draft acquisition spec, run a preview, inspect normalized results, approve the version, and produce durable raw artifacts that a later extractor can consume without depending on Firecrawl internals.
