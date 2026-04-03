# Platform-Control Retool Control Panel

Owner: Platform team
Last reviewed: 2026-04-03
Last verified: 2026-04-03 (repo artifacts and local smoke tests)
Applies to: dev, staging

## Purpose

Document the repo-owned Retool artifacts for the `platform-control` control panel and how they map
to the FastAPI service.

## Source of truth

- Retool manifest: `platform-control/retool/control-panel.manifest.yaml`
- Read queries: `platform-control/retool/sql/`
- Preview workflow: `platform-control/retool/workflows/run_firecrawl_preview.yaml`
- AI copilot prompt: `platform-control/retool/agents/source-setup-copilot.md`
- API contract: `contracts/api/platform-control.openapi.yaml`

## Resource model

- `platform_control_db` is the direct Postgres read resource
- `platform_control_api` is the REST API resource for business actions

This follows ADR-0006: Retool reads directly from Postgres for browse/filter/list screens and uses
the API for stateful actions.

## Control-panel pages

### Reference Data

- Reads jurisdictions and authorities from Postgres
- Uses API actions to create or update reference-data rows

### Sources

- Lists sources and source versions from Postgres
- Uses API actions to create sources, create versions, and edit draft or rejected versions

### Preview Review

- Lists captured resources directly from Postgres
- Calls `GET /v1/runs/{run_id}/preview-summary` for operator-facing heuristics and drift checks
- Calls `POST /v1/runs` for preview creation and `POST /v1/runs/{run_id}/cancel` for operator stop

### Runs

- Lists runs from Postgres
- Calls the API for run status and preview summary detail

## AI setup flow

`Source Setup Copilot` is intentionally bounded. It can help create draft setup, trigger preview,
and summarize output, but it cannot approve versions or launch production runs.

## Verification

- [x] Repo contains versioned Retool artifacts
- [x] Preview workflow maps to current API routes
- [x] Local smoke tests cover preview completion, preview summary, and failed preview handling
