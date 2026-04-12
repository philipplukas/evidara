# MVP Acceptance Scenario Pack (dev-first; optional staging)

Owner: Platform team
Last reviewed: 2026-04-11  
Last verified: 2026-04-11  
Applies to: dev, staging

## Automation

Repeatable HTTP checks (scenarios 1–4) for dev or staging:

```bash
uv run evidara workflow mvp-acceptance
uv run evidara workflow mvp-acceptance --human
./scripts/mvp-acceptance-scenario-pack.sh dev
./scripts/mvp-acceptance-scenario-pack.sh staging
./scripts/mvp-acceptance-scenario-pack.sh dev --json
```

Preferred surface: [`tools/evidara-cli`](../../tools/evidara-cli/README.md) via `evidara workflow mvp-acceptance`.

Lower-level helper: `scripts/mvp-acceptance-scenario-pack.sh` remains available when you want a shell-only version of the same API-oriented checks.

The shell helper requires `curl`, `jq`, and `gcloud`. For **private** Cloud Run APIs, see [Cloud Run auth](#cloud-run-auth-local-and-cli) below.

### CLI output modes (`evidara workflow mvp-acceptance`)

- default: single-line JSON for agents, CI notes, or follow-on tooling
- `--human`: pretty-printed JSON for operators
- `evidence_pack_version` in the JSON payload identifies the acceptance bundle revision (tie-break when comparing archived outputs).

### Cloud Run auth (local and CLI)

API services use **audience-scoped Google ID tokens** at the Cloud Run layer. A normal `gcloud auth login` user often **cannot** run `gcloud auth print-identity-token --audiences=https://…run.app` (service account required). Use one of:

1. **`EVIDARA_GCP_IMPERSONATE_SERVICE_ACCOUNT`** — set to the same service account email used in CI (GitHub secrets `GCP_SERVICE_ACCOUNT_DEV` / `GCP_SERVICE_ACCOUNT_STAGING` when staging exists); your user needs `roles/iam.serviceAccountTokenCreator` on that SA. Then run `./scripts/mvp-acceptance-scenario-pack.sh dev` (or `staging`) or [`scripts/e2e-smoke-test.sh`](../../scripts/e2e-smoke-test.sh) (see script headers).
2. **Pre-minted tokens for evidara-cli** — mint **two** tokens (platform-control and legal-search have **different** audiences = different base URLs), then:

   ```bash
   export EVIDARA_PLATFORM_CONTROL_URL="https://…platform-control-api-staging….run.app"
   export EVIDARA_LEGAL_SEARCH_URL="https://…legal-search-api-staging….run.app"
   export EVIDARA_PLATFORM_CONTROL_TOKEN="$(gcloud auth print-identity-token --impersonate-service-account="$SA" --audiences="$EVIDARA_PLATFORM_CONTROL_URL")"
   export EVIDARA_LEGAL_SEARCH_TOKEN="$(gcloud auth print-identity-token --impersonate-service-account="$SA" --audiences="$EVIDARA_LEGAL_SEARCH_URL")"
   # Optional app-layer keys if the deployment enforces them:
   # export EVIDARA_PLATFORM_CONTROL_API_KEY=…
   uv run evidara workflow mvp-acceptance --human
   ```

3. **Helper:** `source` the output of [`scripts/mint-cloud-run-tokens.sh`](../../scripts/mint-cloud-run-tokens.sh) (see script usage).

Reference: audience-scoped token step in [`.github/workflows/e2e-smoke-staging.yml`](../../.github/workflows/e2e-smoke-staging.yml) (`--impersonate-service-account` + `--audiences`).

### Shell helper output modes (`mvp-acceptance-scenario-pack.sh`)

- default: human-readable terminal summary for operators
- `--json`: machine-readable summary for agents, CI notes, or follow-on tooling

Scenario 5 remains browser-verified in the canonical interaction-flow lane (see [`docs/runbooks/interaction-flow-validation.md`](interaction-flow-validation.md) and the Playwright control-panel test in `legal-search/frontend/e2e/smoke.spec.ts`).

## Purpose

Provide a repeatable acceptance pack for the locked MVP flow:

`ingest source -> version approve -> run -> DI outputs -> searchable detail`

This pack is designed to be executed in **dev** first. Teams with a staging GCP project repeat there for parity evidence; **dev-first** teams attach the **dev** run as the remote acceptance record (see [Environment strategy](../setup/environment-strategy.md#operator-posture-dev-first-no-staging-gcp-project)).

## Preconditions

- `Release Readiness` latest strict run is `GO`.
- Caller has valid identity token access for Cloud Run services.
- Runtime services are healthy in target environment.

## Evidence Ownership

Use these surfaces as the source of truth for each evidence type:

- API acceptance evidence: this runbook plus `uv run evidara workflow mvp-acceptance`
- Browser interaction evidence: [`docs/runbooks/interaction-flow-validation.md`](interaction-flow-validation.md)
- Release sign-off evidence: latest strict `Release Readiness` workflow run

This runbook is intentionally limited to API and proxy-path confidence. It does not replace browser-visible validation or release-lane sign-off.

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
  - `id` matching the requested document id
  - non-empty `title`
  - non-empty `subtitle`
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

## Latest Verification Evidence (2026-04-08)

Evidence produced by `./scripts/mvp-acceptance-scenario-pack.sh` (dev + staging).

### Repo validation (2026-04-09)

- `tools/evidara-cli` contract test for the `mvp-acceptance` workflow payload:  
  `cd tools/evidara-cli && uv run pytest tests/test_workflow_cmd.py -q`
- **Staging refresh:** with `EVIDARA_PLATFORM_CONTROL_URL`, `EVIDARA_LEGAL_SEARCH_URL`, `EVIDARA_LEGAL_SEARCH_FRONTEND_URL`, `EVIDARA_PLATFORM_CONTROL_ADMIN_URL`, and auth vars (`EVIDARA_PLATFORM_CONTROL_TOKEN`, `EVIDARA_LEGAL_SEARCH_TOKEN`, optional API keys) pointed at **staging**, run `uv run evidara workflow mvp-acceptance --human` and attach the summary (or `--json` output) to Linear **TAR-85**.

### Environment health

| Environment | platform-control `/health` | legal-search `/health` |
|---|---|---|
| dev | 200 | 200 |
| staging | 200 | 200 |

### Query pack totals

| Query | dev totalResults | staging totalResults |
|---|---:|---:|
| `art 754` | 13 | 6 |
| `haftung` | 13 | 6 |
| `obligationenrecht` | 13 | 6 |
| `switzerland` | 13 | 6 |

### Detail fetch validation

| Environment | Document ID | `/v1/documents/{id}` | id match, title, subtitle, metadata[], tabs[] |
|---|---|---|---|
| dev | `doc_1gb582v3a8y213hvg3p0n0zk01` | 200 | present |
| staging | `doc_49n3ksesast1e2gbw1b7zev9q7` | 200 | present |

### Website proxy validation

| Environment | legal-search UI root | legal-search UI `/v1/search` | admin UI root | admin UI `/api/platform-control/v1/sources` |
|---|---:|---:|---:|---:|
| dev | 200 | 200 | 200 | 200 |
| staging | 200 | 200 | 200 | 200 |

### UI to admin navigation validation

Canonical browser evidence lives in [`docs/runbooks/interaction-flow-validation.md`](interaction-flow-validation.md).

Automated: Playwright `@smoke` `exposes control panel entrypoint in header` ([`legal-search/frontend/e2e/smoke.spec.ts`](../../legal-search/frontend/e2e/smoke.spec.ts)) with `NEXT_PUBLIC_CONTROL_PANEL_URL` / `PLAYWRIGHT_EXPECTED_CONTROL_PANEL_URL`. Run locally via `npm run e2e:smoke` in `legal-search/frontend`.

| Environment | legal-search header link | link target |
|---|---|---|
| dev | verify in deployed UI with configured env | equals `NEXT_PUBLIC_CONTROL_PANEL_URL` |
| staging | verify in deployed UI with configured env | equals `NEXT_PUBLIC_CONTROL_PANEL_URL` |

### Release readiness parity

Use the latest strict `Release Readiness` run as the sign-off surface, with this runbook attached as API evidence and [`docs/runbooks/interaction-flow-validation.md`](interaction-flow-validation.md) attached as browser evidence.

Historical reference:

- Strict `GO`: [run 24028370655](https://github.com/philipplukas/evidara/actions/runs/24028370655)
- Investigation `GO`: [run 24028371278](https://github.com/philipplukas/evidara/actions/runs/24028371278)

## Exit Criteria

- All scenarios pass in dev and staging.
- No unresolved `severity:blocker` findings remain for user-facing walkthrough.
- Evidence links are attached to active product phase issues.

## M5 Linear evidence

For TAR-64 / TAR-77 / TAR-85 attachment steps, see [M5 evidence checklist](m5-evidence-checklist.md).
