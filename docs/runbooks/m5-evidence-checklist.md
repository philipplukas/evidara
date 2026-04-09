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

### Debugging e2e step 7 (DI signals) — order of checks

Work top-down; the script fails when **both** `canonical_ready` processing-status rows **and** `document.processed` lifecycle rows are missing after the wait.

1. **Run completed with captures?** On timeout the script prints `GET /v1/runs/{run_id}` — confirm `status=completed` and `artifacts_count` / `captured_resources_count` are positive. If zero captures, fix acquisition / `SMOKE_SEED_URL` first.
2. **Which service consumes `artifact_bundle.available`?** In GCP, open the subscription on topic `artifact-bundle-available` (unsuffixed dev) and note the push URL. It must hit the **HTTP ingress** service (`…/internal/events/artifact-bundles:process`), not a pull-only worker with no HTTP handler for that path.
3. **DI publishes outbound events:** After processing, document-intelligence must publish to Pub/Sub topics that platform-control subscribes to (`document-processing-status-updated`, `document-processed`). The HTTP ingress path publishes when `DI_GCP_PROJECT_ID` is set and `DI_EVENT_PUBLISHER_BACKEND` is not `noop` / `off` / `none` (topic names: `DI_STATUS_TOPIC_NAME`, `DI_PROCESSED_TOPIC_NAME` or `DI_DOCUMENT_PROCESSED_PUBSUB_TOPIC`). Redeploy `di-consumer` after code changes.
4. **Pub/Sub → platform-control:** Confirm push subscriptions exist for both topics to `platform-control-api` `/v1/di/events/…` (see [`infra/terraform/gcp/runtime_stack/variables.tf`](../../infra/terraform/gcp/runtime_stack/variables.tf)). Inspect **DLQ** subscription message counts if delivery fails (auth, 4xx/5xx).
5. **Push auth to DI and PC:** Subscriptions use OIDC; the target Cloud Run service must allow the push identity (`roles/run.invoker` for the token’s SA). Do **not** set a static `DOCUMENT_INTELLIGENCE_INGEST_BEARER_TOKEN` on the DI ingress service unless Pub/Sub is configured to send that same secret (OIDC Bearer will not match).
6. **Logs:** `gcloud logging read` filtered by `di-consumer` and `platform-control-api` revision around the run’s `completed_at` time; look for 401/500 on ingest or DI event routes.

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
