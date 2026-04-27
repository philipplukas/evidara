# Scripts

Operator-focused entry points (from repo root unless noted).

| Script | Purpose |
|--------|---------|
| [`e2e-smoke-test.sh`](e2e-smoke-test.sh) | Full pipeline smoke vs Cloud Run (`--env dev\|staging\|prod`). Private Run: set `EVIDARA_GCP_IMPERSONATE_SERVICE_ACCOUNT` or `E2E_PC_ID_TOKEN` / `E2E_LS_ID_TOKEN`. |
| [`mvp-acceptance-scenario-pack.sh`](mvp-acceptance-scenario-pack.sh) | HTTP scenarios 1–4 for dev/staging; same impersonation env as e2e. |
| [`mint-cloud-run-tokens.sh`](mint-cloud-run-tokens.sh) | Prints `export …` lines for `EVIDARA_PLATFORM_CONTROL_TOKEN`, `EVIDARA_LEGAL_SEARCH_TOKEN`, `E2E_PC_ID_TOKEN`, `E2E_LS_ID_TOKEN`. |
| [`evidara-cloud-run-operator-session.sh`](evidara-cloud-run-operator-session.sh) | **One-shot:** `gcloud auth login` if needed, discover Cloud Run URLs, mint tokens, `evidara workflow mvp-acceptance`, optional relevance pack. Defaults to **`dev`** (use `staging` only if operated). See [GCP local Cloud Run auth](../docs/setup/gcp-local-cloud-run-auth.md) §4.1. |
| [`ensure-evidara-cli-auth.sh`](ensure-evidara-cli-auth.sh) | Interactive **gh**, **gcloud** (user + optional ADC), and **databricks** profile login before operator scripts. |
| [`export-databricks-auth-env.sh`](export-databricks-auth-env.sh) | Prints `export DATABRICKS_HOST=…` / `DATABRICKS_TOKEN=…` from `databricks auth env` for a profile (`eval "$(… --profile dev)"`). |
| [`sync-databricks-cluster-policy-github-secret.sh`](sync-databricks-cluster-policy-github-secret.sh) | `databricks cluster-policies list` + `gh secret set` for `DATABRICKS_COMPUTE_GUARDRAILS_POLICY_ID` (dry-run unless `--apply`). |
| [`sync-github-cd-config.sh`](sync-github-cd-config.sh) | Syncs GitHub Actions variables/secrets from **gcloud** + **Databricks**; reads Databricks hosts from env tfvars by default, supports **staging**, optional **`--sync-databricks-compute-policy-ids`**, `--databricks-token-source profile`. |
| [`smoke-evidara-cli.sh`](smoke-evidara-cli.sh) | Local/API `evidara` pings when `EVIDARA_CLI_SMOKE=1`. |
| [`analyze_github_actions_queue.py`](analyze_github_actions_queue.py) | Summarize GitHub Actions **queue vs run** time via `gh` (`--csv`, `--per-job`, `--aggregate-jobs`). See [CI Actions duration metrics](../docs/runbooks/ci-actions-duration-metrics.md). |
| [`validate_k8s_gitops_kustomize.sh`](validate_k8s_gitops_kustomize.sh) | Renders `k8s/gitops/{dev,staging,prod}` with `kubectl kustomize` (skips if `kubectl` missing locally; required in CI). |
| [`run-staging-relevance-query-pack.sh`](run-staging-relevance-query-pack.sh) | Staging `GET /v1/search` top-3 table for **TAR-82** / **TAR-68** (needs `EVIDARA_LEGAL_SEARCH_URL` + token). |
| [`fixtures/internal-beta-staging-queries.txt`](fixtures/internal-beta-staging-queries.txt) | Hetzner internal-beta query pack for the deterministic seeded document. |
| [`preflight-cross-surface-live.sh`](preflight-cross-surface-live.sh) | Local readiness check for the legal-search frontend, control-panel admin, legal-search API, and supporting search stack. |
| [`dev-cross-surface-live.sh`](dev-cross-surface-live.sh) | One-command live local workflow: lean backend stack + legal-search frontend + control-panel admin, with preflight wait. |
| [`lawyer-journey-kpis.py`](lawyer-journey-kpis.py) | Compute funnel KPIs (search→focus rate, reset frequency, refinement depth) from JSONL analytics events on stdin. Example: `cat events.jsonl \| python3 scripts/lawyer-journey-kpis.py`. |

Auth details: [docs/setup/gcp-local-cloud-run-auth.md](../docs/setup/gcp-local-cloud-run-auth.md) and [docs/runbooks/mvp-acceptance-scenario-pack.md](../docs/runbooks/mvp-acceptance-scenario-pack.md).
