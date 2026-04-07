# MVP Acceptance Scenario Pack (Dev -> Staging)

Owner: Platform team
Last reviewed: 2026-04-06
Last verified: 2026-04-06
Applies to: dev, staging

## Purpose

Provide a repeatable acceptance pack for the locked MVP flow:

`ingest source -> version approve -> run -> DI outputs -> searchable detail`

This pack is designed to be executed in dev first, then repeated in staging
with parity evidence.

## Preconditions

- `Release Readiness` latest strict run is `GO`.
- Caller has valid identity token access for Cloud Run services.
- Runtime services are healthy in target environment.

## Scenario Checklist

### Scenario 1: Platform Control surface is operational

- Call `GET /health` on `platform-control-api-{env}` -> expected `200`
- Call `GET /v1/sources` on `platform-control-api-{env}` -> expected `200`

### Scenario 2: Search surface returns stable query results

- Call `GET /v1/search?q=<query>` on `legal-search-api-{env}` -> expected `200`
- Run query pack:
  - `art 754`
  - `haftung`
  - `obligationenrecht`
  - `switzerland`

### Scenario 3: Search result can open detail

- Take first result `id` from scenario 2
- Call `GET /v1/documents/{id}` on `legal-search-api-{env}` -> expected `200`
- Verify response includes:
  - `id`, `title`, `subtitle`
  - `metadata[]`
  - `tabs[]`

### Scenario 4: Website surfaces proxy correctly

- Call legal-search frontend root (`/`) -> expected `200`
- Call legal-search frontend proxied search (`/v1/search?q=<query>`) -> expected `200`
- Call admin frontend root (`/`) -> expected `200`
- Call admin frontend proxied sources (`/api/platform-control/v1/sources`) -> expected `200`

### Scenario 5: Legal-search header exposes admin entrypoint

- Load legal-search frontend root (`/`) with `NEXT_PUBLIC_CONTROL_PANEL_URL` configured
- Verify header shows control-panel link label
- Verify link target equals configured admin URL

## Latest Verification Evidence (2026-04-06)

### Environment health

| Environment | platform-control `/health` | legal-search `/health` |
|---|---|---|
| dev | 200 | 200 |
| staging | 200 | 200 |

### Query pack totals

| Query | dev totalResults | staging totalResults |
|---|---:|---:|
| `art 754` | 11 | 3 |
| `haftung` | 11 | 3 |
| `obligationenrecht` | 11 | 3 |
| `switzerland` | 11 | 3 |

### Detail fetch validation

| Environment | Document ID | `/v1/documents/{id}` |
|---|---|---|
| dev | `doc_1gb582v3a8y213hvg3p0n0zk01` | 200 |
| staging | `doc_49n3ksesast1e2gbw1b7zev9q7` | 200 |

### Website proxy validation

| Environment | legal-search UI root | legal-search UI `/v1/search` | admin UI root | admin UI `/api/platform-control/v1/sources` |
|---|---:|---:|---:|---:|
| dev | 200 | 200 | 200 | 200 |
| staging | 200 | 200 | 200 | 200 |

### UI to admin navigation validation

| Environment | legal-search header link visible | link target configured |
|---|---:|---:|
| dev | pending | pending |
| staging | pending | pending |

### Release readiness parity

- Strict `GO`: [run 24028370655](https://github.com/philipplukas/evidara/actions/runs/24028370655)
- Investigation `GO`: [run 24028371278](https://github.com/philipplukas/evidara/actions/runs/24028371278)

## Exit Criteria

- All scenarios pass in dev and staging.
- No unresolved `severity:blocker` findings remain for user-facing walkthrough.
- Evidence links are attached to active product phase issues.
