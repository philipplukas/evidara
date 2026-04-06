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
| Operator route auth denial parity    | `platform-control/tests/integration/test_auth_route_guards.py`                                   | Service key gets `403` on operator routes; operator key gets `200` |
| Service route auth contract parity   | `platform-control/tests/integration/test_auth_route_guards.py`                                   | Missing/wrong key gets `401`; scoped keys reach handler (`422` with empty payload) |
| CI evidence pack (local CI)          | `.github/workflows/legal-search.yml` (`interaction-flow-evidence` job)                           | Uploaded Playwright reports/results + evidence manifest        |
| CI evidence pack (staging parity)    | `.github/workflows/interaction-flow-staging-evidence.yml`                                        | Smoke+contract suites run against staging frontend/admin URLs with artifacts |

## CI Evidence Automation

- Local/PR workflow: `.github/workflows/legal-search.yml` (`interaction-flow-evidence`)
- Staging parity workflow: `.github/workflows/interaction-flow-staging-evidence.yml`
- Executed suites in both:
  - `npm run e2e:smoke`
  - `npm run e2e:contract`
  - `npm run e2e:screenshot-pack`
- Current staging parity scope:
  - runs stable smoke core journeys and the non-admin hide-link RBAC contract subset
  - full admin-visible link + admin denial UX assertions remain covered in local/PR CI until staging auth/session parity is aligned
- Published artifacts:
  - local: `interaction-flow-evidence-${run_id}`
  - staging: `interaction-flow-staging-evidence-${run_id}`
- Download helper:
  - local evidence: `scripts/fetch-interaction-flow-evidence.sh`
  - staging evidence: `scripts/fetch-interaction-flow-evidence.sh --workflow "Interaction Flow Staging Evidence" --artifact-prefix interaction-flow-staging-evidence`
  - quick-check (recommended): `scripts/check-latest-interaction-flow-evidence.sh --mode staging`
  - screenshot pack output path: `legal-search/frontend/screenshot-pack`

## Canonical Screenshot Evidence Pack

Capture this pack once per release candidate and store it alongside the evidence artifact link.

Automation baseline:

- CI now publishes `legal-search/frontend/screenshot-pack` in both local/PR and staging evidence artifacts.
- Run `scripts/check-latest-interaction-flow-evidence.sh --mode staging` to verify manifest, Playwright report, runbook snapshot, and screenshot pack presence.
- Screenshot pack now includes admin captures for run launch preflight and run lifecycle visibility in addition to legal-search captures.

| Capture point | Target surface | What to capture |
| --- | --- | --- |
| Source + version setup | `platform-control/admin` | Source detail with approved source version selected for launch. |
| Run launch preflight | `platform-control/admin` | Launch dialog readiness status (passed or blocked with remediation details). |
| Run lifecycle visibility | `platform-control/admin` | Run detail showing pipeline health + latest processing/lifecycle timeline evidence. |
| Search discoverability | `legal-search/frontend` | Search results containing the run-scoped indexed document ID. |
| Detail validation | `legal-search/frontend` | Open detail panel for indexed document with metadata + content visible. |
| Cross-surface safety | both | Admin profile link visibility and non-admin denial UX recovery state. |

## Control Panel Testing Policy

- Keep this behavior under test; cross-surface navigation is a user-facing contract, not an optional convenience.
- Treat legal-search header visibility + href as `@contract` coverage (`rbac-cross-surface.spec.ts`), because profile/session wiring can vary by environment.
- Keep admin denial UX (`403` + recovery link) in `@contract` as the minimum cross-surface safety check.
- Reserve `@smoke` for stable app-shell/search journeys and avoid role-dependent assertions unless staging auth/session parity is guaranteed.
- Promote admin-visible link assertions back into staging smoke once cookie/session parity is fully stable in staging.

## Triage Categories

- `broken-implementation`: actual behavior violates expected transition/outcome.
- `ambiguous-requirement`: expected behavior is unclear or contradictory.
- `missing-functionality`: required behavior not implemented yet.

## Run Readiness Remediation (Run/Config Guardrails)

Use `GET /v1/runs/readiness?source_id=<id>&source_version_id=<id>&mode=<preview|production>`
before launch to diagnose blocked runs from control panel preflight checks.

| Readiness code | When it fails | Operator remediation |
| --- | --- | --- |
| `source_exists` | Source ID is missing or deleted | Re-select a valid source in admin; if missing unexpectedly, recreate source and re-link version workflow. |
| `source_version_exists` | Source version ID not found | Re-select an existing source version; if recently removed/superseded, create a new version from the source. |
| `source_version_belongs_to_source` | Version does not belong to selected source | Pick the matching source/version pair from the same source record; do not mix IDs across sources. |
| `mode_compatible_with_version_status` | Mode invalid for current version status (e.g. production on non-approved) | For production runs, approve the version first; for preview, avoid rejected/superseded versions. |
| `acquisition_seed_present` | Acquisition spec has no `seed_url` or `seed_urls` | Edit the source version acquisition spec and add at least one deterministic seed URL, then retry launch. |

## Latest Execution and Triage (2026-04-06)

Executed checks:

- `uv run pytest tests/smoke/test_app.py tests/smoke/test_preview_workflow.py` -> 7 passed
- `npm run e2e:smoke` (`legal-search/frontend`) -> 4 passed
- `npm run e2e:screenshot-pack` (`legal-search/frontend`) -> passed with legal-search + admin captures
- `npm run e2e:visual` (`legal-search/frontend`) -> passed after initializing baseline snapshots
- `Interaction Flow Staging Evidence` workflow run [24046042493](https://github.com/philipplukas/evidara/actions/runs/24046042493) -> passed (smoke + contract subset + screenshot pack)
- evidence quick-check: `scripts/check-latest-interaction-flow-evidence.sh --mode staging --branch main` -> passed (manifest + playwright report + screenshot pack + runbook snapshot)
- `Release Readiness` workflow run [24046126662](https://github.com/philipplukas/evidara/actions/runs/24046126662) -> passed including interaction-flow artifact completeness gate

Classification outcome:

- `broken-implementation`: none observed in critical-path smoke coverage.
- `ambiguous-requirement`:
  - none remaining for non-admin denial UX behavior at admin entry.
- `missing-functionality`:
  - none open; screenshot evidence pack checklist is defined and automated in CI.

## Initial Prioritization Rules

1. P0: flow is blocked for critical path (source/run/search/detail).
2. P1: flow works but operator confidence or correctness is degraded.
3. P2: non-blocking discoverability or workflow friction.

## Current Prioritized Follow-ups

1. P1: run and attach staging parity evidence after each release candidate.
2. P2: keep screenshot pack deterministic and monitor flaky retries in staging evidence runs.
3. P2: align legal-search API docs discoverability expectations (`/docs`) with operator needs.

## RC Dry-Run Procedure (Validated)

Use this sequence for release-candidate confidence:

1. `npm run e2e:screenshot-pack` in `legal-search/frontend`
2. `npm run e2e:visual` in `legal-search/frontend`
3. `scripts/check-latest-interaction-flow-evidence.sh --mode staging --branch main`
4. Trigger `Release Readiness` workflow (`strict=true`) and confirm GO

Latest dry-run evidence:

- screenshot pack + visual checks: local pass on 2026-04-06
- staging evidence workflow: run [24046042493](https://github.com/philipplukas/evidara/actions/runs/24046042493)
- strict release readiness: run [24046126662](https://github.com/philipplukas/evidara/actions/runs/24046126662)

## Weekly KPI Rollup

Generate KPI rollups from recent interaction-flow workflow runs:

- script: `scripts/weekly-interaction-flow-kpis.sh`
- workflow: `.github/workflows/interaction-flow-weekly-kpis.yml`
- output artifact: `interaction-flow-weekly-kpis-{run_id}`

Current KPI set:

- failed staging evidence runs (windowed)
- screenshot-pack retries invoked
- blocked-launch frequency by readiness code (from `operator-journey-events.json`)

Latest KPI snapshot (7-day window, generated 2026-04-06):

| KPI | Value |
| --- | ---: |
| Staging evidence runs inspected | 8 |
| Failed staging evidence runs | 5 |
| Screenshot-pack retries invoked | 0 |
| Blocked-launch frequency (`readiness_codes`) | n/a |

## Recommended Next Expansions (after critical flows are green)

- Expand screenshot evidence pack assertions to include visual diff checks for admin captures.
- Add staging parity run evidence in this file after each release candidate.
