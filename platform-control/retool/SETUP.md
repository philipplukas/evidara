# Platform-Control Retool Setup

## Purpose

Turn the repo-owned Retool artifacts into a working control-panel app for `platform-control`.

This file is the implementation guide for building the Retool app manually from the checked-in
manifest, SQL queries, workflow definition, and agent prompt.

## Source Of Truth

Build the Retool app from these files:

- `control-panel.manifest.yaml`
- `sql/`
- `workflows/run_firecrawl_preview.yaml`
- `agents/source-setup-copilot.md`

This repo does **not** currently store a full Retool app export. The setup is:

- source-controlled at the manifest and artifact level
- environment-specific at the resource-connection level
- manually assembled in Retool

## Required Resources

Create these two Retool resources exactly as named:

### `platform_control_db`

- Type: Postgres
- Purpose: direct read access for browse, detail, and diagnostics screens
- Required connectivity:
  - same database used by `platform-control`
  - access to `sources`, `source_versions`, `runs`, `captured_resources`, `raw_artifacts`,
    `provider_jobs`, `jurisdictions`, and `authorities`

### `platform_control_api`

- Type: REST
- Purpose: business actions and run-scoped read endpoints
- Base URL: the running `platform-control` API
- Authentication: whatever the target environment requires

## App Structure

Create one Retool app with these pages:

1. `Reference Data`
2. `Sources`
3. `Preview Review`
4. `Runs`
5. `Run Detail`

Build them in that order so the shared queries and selection state become reusable as the app grows.

## Page Setup

### 1. Reference Data

Reads:

- `sql/list_jurisdictions.sql`
- `sql/list_authorities.sql`

Actions:

- `createJurisdiction`
- `updateJurisdiction`
- `createAuthority`
- `updateAuthority`

Recommended UI:

- one jurisdictions table
- one authorities table
- inline forms or side-panel forms for create and edit

### 2. Sources

Reads:

- `sql/list_sources.sql`
- `sql/list_source_versions.sql`

Actions:

- `createSource`
- `createSourceVersion`
- `updateSourceVersion`
- `approveSourceVersion`
- `rejectSourceVersion`

Required detail fields for a selected source version:

- `extractor_profile_id`
- `acquisition_spec`

Recommended UI:

- source list on the left
- source-version table scoped by selected `source_id`
- detail panel showing acquisition config JSON and extractor profile value
- action buttons for draft/rejected edit and approve/reject transitions

Required query parameter wiring:

- `list_source_versions.sql` expects `source_id`

### 3. Preview Review

Reads:

- `sql/list_runs.sql`
- `sql/list_run_captured_resources.sql`

Actions:

- `createRun`
- `getRun`
- `getRunPreviewSummary`
- `cancelRun`

Links:

- `Run Detail`

Recommended UI:

- run picker scoped to preview runs
- create-preview form using `mode=preview`
- preview summary panel
- captured-resources table for the selected `run_id`
- open-in-run-detail action for deeper diagnostics

Required query parameter wiring:

- `list_run_captured_resources.sql` expects `run_id`
- preview summary action expects `run_id`
- cancel action expects `run_id`

### 4. Runs

Reads:

- `sql/list_runs.sql`

Actions:

- `createRun`
- `getRun`
- `getRunPreviewSummary`
- `cancelRun`

Links:

- `Run Detail`

Required filter:

- `mode` with values `preview` and `production`

Recommended UI:

- main runs table
- explicit mode filter control
- create-production-run form using `mode=production`
- row actions for open run detail and cancel run

### 5. Run Detail

Reads:

- `sql/list_run_captured_resources.sql`
- `sql/list_run_provider_jobs.sql`
- `sql/list_run_raw_artifacts.sql`

Actions:

- `getRun`
- `getRunPreviewSummary`
- `listRunProcessingStatus`
- `listRunDocumentLifecycle`
- `cancelRun`

Recommended UI sections:

- run summary
- preview summary, shown only for preview runs
- captured resources
- raw artifacts
- provider jobs
- DI processing status
- document lifecycle

Required query parameter wiring:

- all reads and actions on this page should use the selected `run_id`

## Action Mapping

Create the API queries from `control-panel.manifest.yaml` exactly as defined:

- `createJurisdiction` -> `POST /v1/reference-data/jurisdictions`
- `updateJurisdiction` -> `PATCH /v1/reference-data/jurisdictions/{{ jurisdiction_id }}`
- `createAuthority` -> `POST /v1/reference-data/authorities`
- `updateAuthority` -> `PATCH /v1/reference-data/authorities/{{ authority_id }}`
- `createSource` -> `POST /v1/sources`
- `createSourceVersion` -> `POST /v1/sources/{{ source_id }}/versions`
- `updateSourceVersion` -> `PATCH /v1/versions/{{ source_version_id }}`
- `approveSourceVersion` -> `POST /v1/versions/{{ source_version_id }}/approve`
- `rejectSourceVersion` -> `POST /v1/versions/{{ source_version_id }}/reject`
- `createRun` -> `POST /v1/runs`
- `getRun` -> `GET /v1/runs/{{ run_id }}`
- `getRunPreviewSummary` -> `GET /v1/runs/{{ run_id }}/preview-summary`
- `listRunProcessingStatus` -> `GET /v1/runs/{{ run_id }}/processing-status`
- `listRunDocumentLifecycle` -> `GET /v1/runs/{{ run_id }}/document-lifecycle`
- `cancelRun` -> `POST /v1/runs/{{ run_id }}/cancel`

## Workflow Setup

Create one Retool workflow named `run_firecrawl_preview` from
`workflows/run_firecrawl_preview.yaml`.

Expected behavior:

- create or update a draft source version
- trigger a preview run
- fetch run status
- fetch preview summary

Expected outputs:

- `run_id`
- `status`
- `artifacts_count`
- `captured_resources_count`
- `preview_summary`

## Agent Setup

Create one bounded Retool agent named `Source Setup Copilot` from
`agents/source-setup-copilot.md`.

Keep its scope intentionally narrow:

- help create draft setup
- trigger preview
- summarize preview output

Do not extend it to:

- approve source versions
- launch production runs
- perform replay or backfill actions

## Acceptance Checklist

The setup is complete when:

- `Sources` shows sources and source versions from Postgres
- source-version detail shows `extractor_profile_id` and `acquisition_spec`
- `Preview Review` can trigger a preview run and display preview summary data
- `Runs` can filter by `preview` and `production`
- `Runs` can create a production run
- `Run Detail` shows run summary, captured resources, raw artifacts, and provider jobs
- `Run Detail` shows DI processing status and document lifecycle for a run
- replay/backfill controls are absent

## Update Rules

When changing the Retool app shape:

1. update `control-panel.manifest.yaml`
2. update this file if operator setup steps changed
3. update `docs/runbooks/platform-control-retool-control-panel.md` if operator behavior changed
4. add or update tests that validate the manifest shape where practical
