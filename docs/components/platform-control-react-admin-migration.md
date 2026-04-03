# Platform-Control React-Admin Migration

## Purpose

Define the implementation path for replacing the transitional Retool control panel with a fully
code-managed admin app under `platform-control/admin`.

## Current state

`platform-control` currently has:

- a running FastAPI backend
- action-oriented APIs for source lifecycle, approvals, runs, preview summary, and DI monitoring
- a scaffolded `platform-control/admin` app with working `Reference Data`, `Sources`, `Source Versions`, `Preview Review`, `Runs`, `Preview Summary`, and `Run Detail` slices
- repo-owned Retool artifacts kept only as historical reference material
- local Postgres-backed demo support for the current control-plane workflows

The new target is:

- app location: `platform-control/admin`
- frontend stack: `Next.js + React-admin`
- backend: `platform-control` FastAPI only
- browser data access: API only, no direct Postgres reads
- migration mode: phased parity with temporary Retool coexistence

See [ADR-0015](../adr/0015-control-plane-admin-frontend-strategy.md) for the architecture decision.

## Source of truth

- Architecture decision: [ADR-0015](../adr/0015-control-plane-admin-frontend-strategy.md)
- Current platform-control contract: `contracts/api/platform-control.openapi.yaml`
- Current transitional UI artifacts: `platform-control/retool/`
- Canonical architecture model: `structurizr/workspace.dsl`

## Minimal next tasks

- improve source setup ergonomics such as authority/jurisdiction filtering and extractor-profile visibility
- add richer run workflows such as multi-step preview review guidance and tighter operator affordances around run triage
- decide when the remaining Retool artifacts can be fully archived or removed

## Target architecture

### Frontend

- `platform-control/admin` is a separate app within the `platform-control` component boundary
- Use React-admin for resource scaffolding, list/detail/create/edit flows, and operator navigation
- Use Next.js for deployment/runtime consistency with the rest of the repo's frontend work

### Backend

- `platform-control` remains the sole backend for operator actions and read models
- Existing action-oriented endpoints remain in place
- New operator read endpoints are added where the Retool app currently depends on direct SQL reads

### Transition

- Retool artifacts remain archived only until the team decides to delete them entirely
- New operator behavior should prefer the React-admin app once a flow is migrated
- Retool should not gain net-new strategic workflows once the React-admin app work starts

## Repo Layout

Recommended initial layout:

```text
platform-control/
  admin/
    package.json
    tsconfig.json
    next.config.ts
    src/
      app/
      lib/
        admin/
          dataProvider.ts
          authProvider.ts
      resources/
        reference-data/
        sources/
        runs/
```

Implementation defaults:

- package manager: npm to match the rest of the monorepo frontend work
- route strategy: App Router
- API integration: custom React-admin `dataProvider`
- auth handling: start with environment-local dev assumptions, then align with the deployed
  platform-control auth model

## API work required

Existing endpoints already usable by the admin app:

- list jurisdictions
- list authorities
- create/update jurisdictions and authorities
- list/get sources
- list source versions for a source
- create/update/approve/reject source versions
- list runs
- create run
- get run
- list run captured resources
- list run raw artifacts
- list run provider jobs
- cancel run
- get preview summary
- list run processing status
- list run document lifecycle

New endpoints required for parity with the current Retool operator views:

- no additional run-detail read endpoints for the current parity slice
- the next API work should focus on source/reference-data read and mutation coverage for the admin app

Explicit non-goals for the first migration slice:

- direct browser reads from Postgres
- replay/backfill/repair endpoints
- bundle-manifest drilldown
- extractor-profile CRUD

## Later expansion

| Phase | Capability |
|-------|-----------|
| Next | Polish `Runs`, `Run Detail`, and `Preview Review` ergonomics in React-admin |
| Next | Decide whether to archive or remove the remaining Retool artifacts |
| Later | Replay, backfill, and repair flows |
| Later | Bundle-manifest drilldown |
| Later | Extractor-profile CRUD |

## Dependencies

| Dependency | Purpose |
|-----------|---------|
| `platform-control` FastAPI API | All operator reads and actions |
| Next.js | App runtime and routing |
| React-admin | Resource-driven admin scaffolding |
| Local Postgres / Cloud SQL | Backing store for backend read models only |
| Existing contracts | Shared API and event boundary definitions |

## Page migration order

### Phase 1: App foundation

- scaffold `platform-control/admin`
- add React-admin shell, navigation, and layout
- implement shared API client and `dataProvider`
- wire local dev against the Compose-backed `platform-control` API

### Phase 2: Reference Data

- jurisdictions list/create/edit
- authorities list/create/edit

### Phase 3: Sources

- source list and source detail
- source-version list for a selected source
- create version, update draft/rejected version, approve, reject
- show `extractor_profile_id` and acquisition config detail

### Phase 4: Runs

- runs list with explicit `preview` vs `production` filtering
- create production run
- cancel run

### Phase 5: Run Detail

- run summary
- preview summary for preview runs
- captured resources
- raw artifacts
- provider jobs
- processing status
- document lifecycle

### Phase 6: Preview Review

- preview-run creation flow
- preview-summary review UX
- links into Run Detail

### Phase 7: Retool retirement

- confirm parity for the main operator flows
- keep Retool artifacts reference-only
- delete the remaining Retool artifacts once they no longer provide migration value

## Testing

Frontend:

- unit tests for `dataProvider` request/response mapping
- component tests for the main resource views
- one smoke path for:
  - source -> version -> approve
  - production run -> run detail -> DI status visibility

Backend:

- add endpoint tests for new run read surfaces
- keep existing smoke tests for preview and DI event flows
- add contract coverage for any new operator read endpoints

Acceptance criteria:

- an operator can complete the main demo flows in the React-admin app without Retool
- the React-admin app does not require direct database credentials in the browser
- Retool is no longer needed for day-to-day source setup, run launch, or DI monitoring

## Drift risks

| Risk | Mitigation |
|------|-----------|
| Frontend begins depending on database-shaped data instead of stable APIs | Add explicit operator read endpoints and test the `dataProvider` against API contracts |
| Retool and React-admin drift during coexistence | Freeze net-new strategic work in Retool and migrate flows in a fixed order |
| Admin UI leaks into `legal-search` ownership | Keep the app under `platform-control/admin` and preserve the existing component boundary |
| Migration stalls after partial parity | Treat `Runs` and `Run Detail` as required parity milestones before declaring success |

## Open defaults chosen

- Use full React-admin first, not `ra-core`
- Keep the app inside `platform-control`, not `legal-search`
- Add read APIs to `platform-control` rather than preserving the Retool direct-SQL model
