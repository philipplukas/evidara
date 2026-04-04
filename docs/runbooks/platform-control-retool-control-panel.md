# Platform-Control Retool Control Panel (DEPRECATED)

Owner: Platform team
Last reviewed: 2026-04-04
Last verified: 2026-04-03 (repo artifacts and local smoke tests)
Applies to: dev, staging

> **⚠️ DEPRECATED**: Retool is no longer the active operator UI. The React Admin
> app at `platform-control/admin/` is the sole ops interface (see ADR-0015).
> This runbook is retained as historical reference only.

## Purpose

Document the repo-owned Retool artifacts for the `platform-control` control panel and how they map
to the FastAPI service. The primary operator workflow is the code-managed React Admin app in
`platform-control/admin`. This runbook is historical reference only.

## Source of truth

- Retool manifest: `platform-control/retool/control-panel.manifest.yaml`
- Retool setup guide: `platform-control/retool/SETUP.md`
- Read queries: `platform-control/retool/sql/`
- Preview workflow: `platform-control/retool/workflows/run_firecrawl_preview.yaml`
- AI copilot prompt: `platform-control/retool/agents/source-setup-copilot.md`
- API contract: `contracts/api/platform-control.openapi.yaml`
- Local demo setup: `docs/setup/platform-control-local-demo.md`

## Resource model

- `platform_control_db` is the direct Postgres read resource
- `platform_control_api` is the REST API resource for business actions

This follows ADR-0006: Retool reads directly from Postgres for browse/filter/list screens and uses
the API for stateful actions.

## Control-panel pages

Retool pages remain useful for comparison, but `Preview Review`, `Runs`, and `Run Detail` are no
longer the primary documented operator path.

### Reference Data

- Reads jurisdictions and authorities from Postgres
- Uses API actions to create or update reference-data rows

### Sources

- Lists sources and source versions from Postgres
- Uses API actions to create sources, create versions, and edit draft or rejected versions
- Source-version detail shows `extractor_profile_id` and acquisition config for operator review

### Preview Review

- Lists captured resources directly from Postgres
- Calls `GET /v1/runs/{run_id}/preview-summary` for operator-facing heuristics and drift checks
- Calls `POST /v1/runs` for preview creation and `POST /v1/runs/{run_id}/cancel` for operator stop
- Links to `Run Detail` for provider-job and raw-artifact diagnostics

### Runs

- Lists runs from Postgres
- Supports explicit `preview` vs `production` filtering using the persisted `mode` field
- Calls `POST /v1/runs` for operator-triggered production runs
- Links to `Run Detail` for diagnostics and downstream monitoring

### Run Detail

- Calls `GET /v1/runs/{run_id}` for current run status and terminal failure reasons
- Lists captured resources, raw artifacts, and provider jobs directly from Postgres
- Calls `GET /v1/runs/{run_id}/preview-summary` for preview heuristics when the run was launched in preview mode
- Calls `GET /v1/runs/{run_id}/processing-status` and `GET /v1/runs/{run_id}/document-lifecycle` for downstream DI monitoring
- Calls `POST /v1/runs/{run_id}/cancel` for operator stop while a run is still pending or running

## AI setup flow

`Source Setup Copilot` is intentionally bounded. It can help create draft setup, trigger preview,
and summarize output, but it cannot approve versions or launch production runs.

## Historical flow reference

Prefer the React-admin app for these flows. Use the following only when comparing behavior against
the transitional Retool implementation.

### Preview review

1. Open `Sources` and create or select a source plus draft source version.
2. Confirm the source-version detail includes the selected `extractor_profile_id` and acquisition config.
3. Trigger a preview run from `Preview Review`.
4. Review preview heuristics and drift checks.
5. Open `Run Detail` and inspect captured resources, raw artifacts, and provider-job status.

### Production run and DI monitoring

1. Approve a source version from `Sources`.
2. Open `Runs`, filter to `production`, and trigger a production run.
3. Open `Run Detail` for the new run.
4. Confirm run status and provider-job state are visible.
5. Observe downstream DI processing-status updates and document lifecycle events as they arrive.
6. Confirm replay or backfill controls are not shown in the control panel.

## Deferred from this slice

- Replay, backfill, and repair actions
- Extractor-profile CRUD and management
- Bundle-manifest drilldown
- Final archival or deletion of the Retool artifacts

## Verification

- [x] Repo contains versioned Retool artifacts
- [x] Preview workflow maps to current API routes
- [x] Local smoke tests cover preview completion, preview summary, failed preview handling, and run-detail diagnostics data
- [x] Local smoke tests cover production run DI processing-status and lifecycle visibility
