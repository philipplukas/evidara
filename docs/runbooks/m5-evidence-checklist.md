# M5 evidence checklist (operator)

Owner: Platform team  
Last reviewed: 2026-04-09  
Last verified: 2026-04-09  
Applies to: dev, staging (operator evidence for Linear TAR-64 / TAR-77 / TAR-85)

Use this when closing phase-5 Linear items that need **run output or screenshots**, not repo code. GCP IAM and GitHub admin steps cannot be done from git alone.

## TAR-64 — Dev e2e smoke (two runs)

1. Complete [GCP local Cloud Run auth](../setup/gcp-local-cloud-run-auth.md) if calling private Run.
2. **Prerequisite — step 7 (DI signals):** Terraform must provision **push** subscriptions so `document-processing-status-updated` and `document-processed` reach `platform-control-api` (`/v1/di/events/...`). Defaults live in [`infra/terraform/gcp/runtime_stack/variables.tf`](../../infra/terraform/gcp/runtime_stack/variables.tf); environments with suffixed topic names must mirror [`infra/env/staging/runtime.gcp.tfvars.example`](../../infra/env/staging/runtime.gcp.tfvars.example). After changing wiring, `terraform apply` the runtime stack, then confirm subscriptions in GCP console.
3. Optional: set `SMOKE_SEED_URL` to a URL that returns stable `application/json` or HTML from Cloud Run (e.g. an npm registry `latest` JSON URL) if the default seed fails acquisition from the provider’s network.
4. Run **twice** (separate runs for evidence):
   - GitHub: **Actions** → **E2E Smoke Dev** (workflow_dispatch or wait for schedule), **or**
   - Local: `EVIDARA_GCP_IMPERSONATE_SERVICE_ACCOUNT=… GCP_PROJECT_ID=… ./scripts/e2e-smoke-test.sh --env dev`
5. Attach to Linear: artifact logs / run URLs / timestamps scoped to each run.

## TAR-77 — Required check on `main`

1. GitHub **Settings** → **Branches** → branch protection for `main`.
2. Require **Release Readiness** (or your strict gate workflow) as a required status check.
3. Capture a **screenshot** of the rule + a **green** workflow run; attach to TAR-77.

## TAR-85 — Staging MVP acceptance

1. Point CLI at staging base URLs (`EVIDARA_PLATFORM_CONTROL_URL`, `EVIDARA_LEGAL_SEARCH_URL`, frontend/admin URLs per [MVP acceptance scenario pack](mvp-acceptance-scenario-pack.md)).
2. Mint tokens: `eval "$(… ./scripts/mint-cloud-run-tokens.sh)"` or manual `gcloud auth print-identity-token --impersonate-service-account=… --audiences=…` for **each** API host.
3. Add app-layer keys if the deployment requires them (`EVIDARA_PLATFORM_CONTROL_API_KEY`, etc.).
4. Run: `cd tools/evidara-cli && uv run evidara workflow mvp-acceptance --human` (or `--json`).
5. Attach stdout / JSON to TAR-85.

## Related docs

- [Phase 5 go / no-go memo](phase-5-go-no-go-memo.md) — gate table and Linear evidence owners
- [MVP acceptance scenario pack](mvp-acceptance-scenario-pack.md)
- [First vertical slice exit gates](first-vertical-slice-exit-gates.md)
- [Interaction flow validation](interaction-flow-validation.md)
- [GCP local Cloud Run auth](../setup/gcp-local-cloud-run-auth.md)
- [Evidara CLI remote smoke — operator](evidara-cli-remote-smoke-operator.md)
