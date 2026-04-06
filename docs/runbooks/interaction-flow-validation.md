# Interaction Flow Validation (UI <-> Control Panel <-> APIs)

Owner: Platform team  
Last reviewed: 2026-04-06  
Last verified: 2026-04-06  
Applies to: local, dev, staging

## Purpose

Define and validate the highest-risk end-to-end interaction flows across:

- Legal-search UI (`legal-search/frontend`)
- Platform-control admin UI (`platform-control/admin`)
- Platform-control API and legal-search API

This runbook is intentionally risk-first and is used as the acceptance baseline
before adding lower-priority flow coverage.

## Critical User Journeys

1. Source lifecycle setup (admin): create source -> create version -> approve.
2. Run orchestration (admin): trigger run from approved version.
3. DI callback ingest (platform-control): status/lifecycle events are accepted and queryable.
4. Search and detail (user UI): query returns results and detail opens reliably.
5. Cross-surface operator navigation: legal-search header exposes control panel entrypoint.
6. Surface health checks: UI/API health and core routes are reachable.

## Expected Outcomes and State Transitions

### Journey 1: Source lifecycle setup

- Trigger: `POST /v1/sources`, `POST /v1/sources/{id}/versions`, `POST /v1/versions/{id}/approve`
- Expected transitions:
  - source version: `draft` -> `approved`
  - approved versions become immutable for updates
- Evidence endpoint(s): `GET /v1/sources`, version payload from create/approve responses

### Journey 2: Run orchestration

- Trigger: `POST /v1/runs` for approved source version
- Expected transitions:
  - run: `pending` -> `running` -> terminal (`completed` or `failed`)
- Evidence endpoint(s): `GET /v1/runs`, run payload with scope/replay fields

### Journey 3: DI callback ingest

- Trigger: DI event endpoints for `document.processing_status.updated`, `document.processed`, `document.withdrawn`
- Expected transitions:
  - processing status rows appear for run
  - lifecycle events appear in reverse chronological order
- Evidence endpoint(s):
  - `GET /v1/runs/{run_id}/processing-status`
  - `GET /v1/runs/{run_id}/document-lifecycle`

### Journey 4: Search and detail

- Trigger: UI search submit then result selection
- Expected transitions:
  - URL query and selected item state update
  - detail panel opens and closes via keyboard escape
- Evidence endpoint(s): proxied `/v1/search`, `/v1/documents/{id}` and browser state

### Journey 5: Cross-surface operator navigation

- Trigger: open legal-search UI header; optionally open platform-control admin as a non-admin role
- Expected transitions:
  - control panel link is visible when `NEXT_PUBLIC_CONTROL_PANEL_URL` is configured **and** the UI profile is `admin` (see `NEXT_PUBLIC_DEFAULT_UI_PROFILE` and `evidara-ui-profile` in `legal-search/frontend/README.md`)
  - non-admin users who open admin directly see explicit **403-style** denial copy and a recovery link (`AdminShell`)
  - link points to configured admin surface URL for authorized profiles
- Evidence: browser-visible header link with expected href; Playwright `@contract` in `legal-search/frontend/e2e/rbac-cross-surface.spec.ts`

### Journey 6: Surface health checks

- Trigger: health/docs/list endpoints for platform-control and legal-search surfaces
- Expected transitions:
  - health/read endpoints return `200`
  - frontend roots return `200`
- Evidence endpoints:
  - `platform-control`: `/health`, `/v1/sources`
  - `legal-search`: `/v1/search`, `/v1/documents/{id}`

## Repeatable Test Scenarios

| Scenario                             | Test artifact                                                                                   | Pass criteria                                                 |
| ------------------------------------ | ----------------------------------------------------------------------------------------------- | ------------------------------------------------------------- |
| Source lifecycle + run + DI ingest   | `platform-control/tests/smoke/test_app.py::test_create_source_approve_and_trigger_run`          | Full workflow passes with expected state and event assertions |
| Hierarchy sync safety                | `platform-control/tests/smoke/test_app.py::test_sync_hierarchy_endpoint`                        | Dry-run sync returns 200 with non-zero created counts         |
| Preview flow path                    | `platform-control/tests/smoke/test_preview_workflow.py`                                         | Preview mode reaches terminal path with expected records      |
| UI app-shell and search interactions | `legal-search/frontend/e2e/smoke.spec.ts`                                                       | Existing smoke cases pass                                     |
| UI control-panel entrypoint          | `legal-search/frontend/e2e/smoke.spec.ts` (`@smoke exposes control panel entrypoint in header`) | Header link exists and targets configured URL                 |
| RBAC: admin vs standard header       | `legal-search/frontend/e2e/rbac-cross-surface.spec.ts` (`@contract`)                            | Admin sees link; standard cookie hides link                   |
| RBAC: admin surface denial           | `legal-search/frontend/e2e/rbac-cross-surface.spec.ts` (`@contract`)                            | Non-admin env shows denial copy + recovery link               |
| Admin access helpers                 | `platform-control/admin/src/lib/admin/accessControl.test.ts`                                     | Role parsing and allow-list logic                             |
| CI evidence pack                     | `.github/workflows/legal-search.yml` (`interaction-flow-evidence` job)                           | Uploaded Playwright reports/results + evidence manifest        |

## CI Evidence Automation

- Workflow: `.github/workflows/legal-search.yml`
- Job: `interaction-flow-evidence`
- Trigger paths include this runbook (`docs/runbooks/interaction-flow-validation.md`) plus legal-search/admin surfaces
- Executed suites:
  - `npm run e2e:smoke`
  - `npm run e2e:contract`
- Published artifact: `interaction-flow-evidence-${run_id}` containing:
  - `legal-search/frontend/playwright-report`
  - `legal-search/frontend/test-results`
  - `legal-search/frontend/interaction-flow-evidence.md`
  - `docs/runbooks/interaction-flow-validation.md`

## Triage Categories

- `broken-implementation`: actual behavior violates expected transition/outcome.
- `ambiguous-requirement`: expected behavior is unclear or contradictory.
- `missing-functionality`: required behavior not implemented yet.

## Latest Execution and Triage (2026-04-06)

Executed checks:

- `uv run pytest tests/smoke/test_app.py tests/smoke/test_preview_workflow.py` -> 7 passed
- `npm run e2e:smoke` (`legal-search/frontend`) -> 4 passed

Classification outcome:

- `broken-implementation`: none observed in critical-path smoke coverage.
- `ambiguous-requirement`:
  - none remaining for non-admin denial UX behavior at admin entry.
- `missing-functionality`:
  - backend-enforced authorization parity for admin endpoints (in addition to UI denial UX).
  - canonical screenshot evidence pack for operator walkthrough.

## Initial Prioritization Rules

1. P0: flow is blocked for critical path (source/run/search/detail).
2. P1: flow works but operator confidence or correctness is degraded.
3. P2: non-blocking discoverability or workflow friction.

## Current Prioritized Follow-ups

1. P1: enforce backend authorization parity for admin surface and APIs.
2. P2: capture and store screenshot evidence pack for walkthrough parity.
3. P2: align legal-search API docs discoverability expectations (`/docs`) with operator needs.

## Recommended Next Expansions (after critical flows are green)

- Add backend-enforced role denial scenario for non-admin users attempting admin navigation.
- Add screenshot evidence pack for the operator walkthrough.
- Add staging parity run evidence in this file after each release candidate.
