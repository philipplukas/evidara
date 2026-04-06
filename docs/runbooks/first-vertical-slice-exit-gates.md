# First Vertical Slice Exit Gates

Owner: Platform team
Last reviewed: 2026-04-05
Last verified: 2026-04-06
Applies to: dev, staging, prod

This runbook defines the minimum verification set to declare the first Evidara vertical slice ready.

## Scope

The gate covers:

1. `platform-control` run and bundle publication
2. `document-intelligence` bundle processing and publication events
3. `legal-search` projection ingest and search/query behavior

## Required Runtime Wiring

- Runtime stack includes Cloud Run services for:
  - `platform-control-api`
  - `platform-control-worker`
  - `document-intelligence-consumer`
  - `legal-search-api`
- Pub/Sub subscriptions are present:
  - `document-intelligence-artifact-bundle-available`
  - `platform-control-document-processing-status-updated`
  - `legal-search-document-processed`
  - `legal-search-document-withdrawn`
- OpenSearch runtime target and aliases exist for the active environment.

## Exit Gate Checklist

### Gate A: Platform-Control

- Create source, source version, and run.
- Firecrawl webhook path registers raw artifacts and publishes immutable bundle manifest.
- `artifact_bundle.available` event is emitted with:
  - run/source/source-version provenance
  - `reference_snapshot_set_ref` populated in manifest `reference_context`.

### Gate B: Document-Intelligence

- `document-intelligence-consumer` receives `artifact_bundle.available`.
- Canonical `Document`, `Section`, and `ProcessingManifest` records are written.
- `document.processing_status.updated` and `document.processed` events are emitted.

### Gate C: Legal-Search

- `document.processed` is accepted by projection endpoint and upserted.
- `document.withdrawn` de-indexes/tombstones the projection.
- Projection history tracks idempotency and stale revision handling.
- Search/detail queries return the indexed document through alias-backed indices.

### Gate D: Run-Scoped Smoke Assertions

- Smoke verification must use run-scoped assertions, not global stats.
- Projection verification must query `GET /v1/projections/events/history?run_id=<run_id>`.
- Search verification must confirm the exact `document_id` from the run-scoped
  projection history appears in `/v1/search` results.
- Release checklist must include the latest interaction-flow evidence artifact:
  - local/PR evidence: `scripts/fetch-interaction-flow-evidence.sh`
  - staging parity evidence: `scripts/fetch-interaction-flow-evidence.sh --workflow "Interaction Flow Staging Evidence" --artifact-prefix interaction-flow-staging-evidence`
- Fast verification command (recommended):
  - `scripts/check-latest-interaction-flow-evidence.sh --mode staging`
  - expected files:
    - `legal-search/frontend/interaction-flow-staging-evidence.md`
    - `legal-search/frontend/playwright-report`
    - `legal-search/frontend/screenshot-pack`
    - `docs/runbooks/interaction-flow-validation.md`

## Local Verification Commands

Run these checks before marking a slice validation complete:

```bash
cd evidara/legal-search/api
npm test -- --run src/modules/projections/projections.service.spec.ts
```

```bash
cd evidara/platform-control
uv run pytest tests/unit/test_firecrawl_webhook_service.py -q
```

Optionally run full component gates:

```bash
cd evidara
bash scripts/check-platform-control.sh
bash scripts/check-document-intelligence.sh
bash scripts/check-legal-search.sh
```

For vertical-slice runtime verification in dev, use:

```bash
cd evidara
GCP_PROJECT_ID=project-dacd6b7b-dc96-4534-b82 \
SMOKE_SEED_URL=http://example.org \
SMOKE_REQUEST_TIMEOUT_SECONDS=10 \
scripts/e2e-smoke-test.sh --env dev
```

## Verification Log

Recent closure evidence for this slice:

| Date | Change | Evidence |
|------|--------|----------|
| 2026-04-05 | PR [#90](https://github.com/philipplukas/evidara/pull/90) merged (`test: make e2e smoke assertions run-scoped`) | Run-scoped projection + search assertions active in smoke script |
| 2026-04-05 | PR [#91](https://github.com/philipplukas/evidara/pull/91) merged (`test: stabilize e2e smoke seed configuration`) | Configurable smoke seed/timeout and Step 9 parse fix |
| 2026-04-05 | PR [#94](https://github.com/philipplukas/evidara/pull/94) merged (`fix: explicit OIDC auth for e2e smoke workflow`) | Workflow mints per-service audience-scoped tokens and smoke script routes auth deterministically by service URL |
| 2026-04-05 | PR [#95](https://github.com/philipplukas/evidara/pull/95) merged (`fix: use SA impersonation for smoke OIDC tokens`) | Token minting switched to service-account impersonation to support WIF-based GitHub Actions credentials |
| 2026-04-05 | Post-merge smoke pass | GitHub Actions run [24009644603](https://github.com/philipplukas/evidara/actions/runs/24009644603) passed all steps (DI preflight, token minting, smoke run, artifact upload) |
| 2026-04-06 | Staging interaction-flow parity sanity rerun | GitHub Actions run [24043317173](https://github.com/philipplukas/evidara/actions/runs/24043317173) passed smoke subset + cross-surface contract subset and uploaded `interaction-flow-staging-evidence-24043317173` |

## Ownership Handoff

| Area | Primary owner | Backup owner | Trigger |
|------|---------------|--------------|---------|
| Dev smoke workflow failures (`.github/workflows/e2e-smoke-dev.yml`) | Platform team | Document-intelligence team | Any failed scheduled/manual smoke run |
| DI surface schema drift preflight (`scripts/check-di-surface-schema-drift.sh`) | Document-intelligence team | Platform team | Preflight fail or repeated optional-column warnings followed by write errors |
| Pub/Sub backlog and DLQ hygiene | Platform team | Legal-search team | Undelivered backlog growth, DLQ accumulation, replay required |

## Replay / Recovery Acceptance Criteria

Replay/recovery is accepted for the first vertical slice when all criteria below are met.

### R1: Replay provenance is explicit and queryable

- Every replayed run must persist `scope` + `replay` metadata on `Run.run_metadata`.
- `replay.mode` and `replay.parent_run_id` (where required) must be visible via `GET /v1/runs` and `GET /v1/runs/{id}`.
- Validation coverage:
  - `platform-control/tests/unit/test_run_service.py::test_create_run_persists_explicit_scope_and_replay_metadata`
  - `platform-control/tests/unit/test_run_service.py::test_partial_rerun_requires_parent_run_id`

### R2: Safe retry preconditions are enforced

- Retry must only be allowed from terminal failure states (`failed`, `cancelled`).
- Retried runs must reset dispatch-critical fields (`status`, timestamps, `failure_reason`) before re-dispatch.
- Validation coverage:
  - `platform-control/tests/unit/test_run_service.py::test_retry_run_resets_failed_run_to_pending`
  - `platform-control/tests/unit/test_run_service.py::test_retry_run_rejects_non_terminal_states`

### R3: Idempotent and stale-safe processing behavior

- Processing updates must be append-only and keyed by event identity.
- Projection/search checks in smoke must be run-scoped so recovery verification does not rely on global counters.
- Validation coverage:
  - run-scoped smoke assertions in `scripts/e2e-smoke-test.sh`
  - Gate D requirements in this runbook (`/v1/projections/events/history?run_id=<run_id>`)

### R4: Incident-recovery drill (manual, per release candidate)

- Execute one controlled replay drill on staging:
  1. Trigger a preview run.
  2. Trigger a replay run using explicit `replay` metadata.
  3. Verify lifecycle/processing visibility and run-scoped search evidence for the replayed run.
- Attach evidence links (run IDs + workflow/artifact URL) to the Verification Log table before release sign-off.
