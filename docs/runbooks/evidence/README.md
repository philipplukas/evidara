# Operator evidence snapshots

Committed JSON/Markdown captures for release gates (TAR-64, TAR-85, TAR-82, TAR-68). **No secrets** — only public HTTP responses and workflow summaries.

Refresh when staging URLs or corpus change. URLs are taken from [`infra/env/staging/runtime.gcp.tfvars.example`](../../../infra/env/staging/runtime.gcp.tfvars.example) (example Cloud Run hostnames).

| File | Purpose |
|------|---------|
| `2026-04-09-dev-e2e-smoke-blocker.md` | Why dev `e2e-smoke-test.sh` was not executed from this environment |
| `2026-04-09-staging-mvp-acceptance-run1.json` | `evidara workflow mvp-acceptance` against staging (run 1) |
| `2026-04-09-staging-mvp-acceptance-run2.json` | Same workflow, second run (correlation id varied) |
| `2026-04-09-staging-relevance-pack.md` | Staging search top-3 IDs per suggested query |
| `2026-04-09-staging-relevance-pack-rerun.md` | Same, regenerated via `scripts/capture-staging-relevance-pack.sh` |
| `2026-04-13-dev-mvp-acceptance-run1.json` | Fresh dev `evidara workflow mvp-acceptance` capture after the CI/auth fix landed |
| `2026-04-13-dev-relevance-pack.md` | Historical dev relevance pack before the 2026-04-14 refresh; `q=*` was empty |
| `2026-04-14-dev-relevance-pack.md` | Canonical dev relevance evidence refresh: `q=*` is non-empty, CH recovered, AT still `RIS Dokument`, broader ranking remains open |
| `2026-04-09-e2e-github-dispatch-tar64.md` | Two `gh workflow run` E2E Smoke Dev attempts + outcomes |
| `2026-04-09-e2e-step7-investigation.md` | Dev: Pub/Sub wiring OK; `di-consumer-dev` HTTP 500 on bundle ingress; DLQ note; next actions |
