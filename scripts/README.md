# Scripts

Operator-focused entry points (from repo root unless noted).

| Script | Purpose |
|--------|---------|
| [`e2e-smoke-test.sh`](e2e-smoke-test.sh) | Full pipeline smoke vs Cloud Run (`--env dev\|staging\|prod`). Private Run: set `EVIDARA_GCP_IMPERSONATE_SERVICE_ACCOUNT` or `E2E_PC_ID_TOKEN` / `E2E_LS_ID_TOKEN`. |
| [`mvp-acceptance-scenario-pack.sh`](mvp-acceptance-scenario-pack.sh) | HTTP scenarios 1–4 for dev/staging; same impersonation env as e2e. |
| [`mint-cloud-run-tokens.sh`](mint-cloud-run-tokens.sh) | Prints `export …` lines for `EVIDARA_PLATFORM_CONTROL_TOKEN`, `EVIDARA_LEGAL_SEARCH_TOKEN`, `E2E_PC_ID_TOKEN`, `E2E_LS_ID_TOKEN`. |
| [`evidara-cloud-run-operator-session.sh`](evidara-cloud-run-operator-session.sh) | **One-shot:** `gcloud auth login` if needed, discover Cloud Run URLs, mint tokens, `evidara workflow mvp-acceptance`, optional relevance pack. Defaults to **`dev`** (use `staging` only if operated). See [GCP local Cloud Run auth](../docs/setup/gcp-local-cloud-run-auth.md) §4.1. |
| [`ensure-evidara-cli-auth.sh`](ensure-evidara-cli-auth.sh) | Interactive **gh** and **gcloud** (user + optional ADC) login before operator scripts. |
| [`sync-github-cd-config.sh`](sync-github-cd-config.sh) | Syncs GitHub Actions variables/secrets from **gcloud**; supports **staging**. |
| [`smoke-evidara-cli.sh`](smoke-evidara-cli.sh) | Local/API `evidara` pings when `EVIDARA_CLI_SMOKE=1`. |
| [`analyze_github_actions_queue.py`](analyze_github_actions_queue.py) | Summarize GitHub Actions **queue vs run** time via `gh` (`--csv`, `--per-job`, `--aggregate-jobs`). See [CI Actions duration metrics](../docs/runbooks/ci-actions-duration-metrics.md). |
| [`validate_k8s_gitops_kustomize.sh`](validate_k8s_gitops_kustomize.sh) | Renders `k8s/gitops/{dev,staging,prod}` with `kubectl kustomize` (skips if `kubectl` missing locally; required in CI). |
| [`run-staging-relevance-query-pack.sh`](run-staging-relevance-query-pack.sh) | Staging `GET /v1/search` top-3 table for **TAR-82** / **TAR-68** (needs `EVIDARA_LEGAL_SEARCH_URL` + token). |
| [`check-internal-beta-query-pack.sh`](check-internal-beta-query-pack.sh) | Hetzner internal-beta assertion gate: top-5 query expectations, exact `q=*` source-derived corpus, detail metadata/tabs, and retired synthetic `404`s. |
| [`prove-internal-beta-normal-replay.sh`](prove-internal-beta-normal-replay.sh) | Operator proof for platform-control local outbox → DI replay → legal-search projection cleanup while preserving the exact internal-beta corpus. |
| [`fixtures/internal-beta-staging-queries.txt`](fixtures/internal-beta-staging-queries.txt) | Hetzner internal-beta query pack for the deterministic seeded corpus. |
| [`fixtures/internal-beta-normal-replay-targets.tsv`](fixtures/internal-beta-normal-replay-targets.tsv) | Fedlex URLs used by the normal replay proof for the same 12 beta documents. |
| [`fixtures/internal-beta-expansion-normal-replay-targets.tsv`](fixtures/internal-beta-expansion-normal-replay-targets.tsv) | Fedlex SPARQL source-derived expansion targets used to test normal replay beyond the canonical 12-document corpus. |
| [`fixtures/internal-beta-staging-expected.tsv`](fixtures/internal-beta-staging-expected.tsv) | Expected top-5 document IDs for the internal-beta seeded corpus. |
| [`fixtures/internal-beta-staging-documents.tsv`](fixtures/internal-beta-staging-documents.tsv) | Detail metadata expectations for the source-derived Fedlex beta corpus. |
| [`fixtures/internal-beta-staging-withdrawn-documents.txt`](fixtures/internal-beta-staging-withdrawn-documents.txt) | Retired synthetic beta document IDs that must return `404` from legal-search detail. |
| [`preflight-cross-surface-live.sh`](preflight-cross-surface-live.sh) | Local readiness check for the legal-search frontend, control-panel admin, legal-search API, and supporting search stack. |
| [`dev-cross-surface-live.sh`](dev-cross-surface-live.sh) | One-command live local workflow: lean backend stack + legal-search frontend + control-panel admin, with preflight wait. |
| [`lawyer-journey-kpis.py`](lawyer-journey-kpis.py) | Compute funnel KPIs (search→focus rate, reset frequency, refinement depth) from JSONL analytics events on stdin. Example: `cat events.jsonl \| python3 scripts/lawyer-journey-kpis.py`. |

Auth details: [docs/setup/gcp-local-cloud-run-auth.md](../docs/setup/gcp-local-cloud-run-auth.md) and [docs/runbooks/mvp-acceptance-scenario-pack.md](../docs/runbooks/mvp-acceptance-scenario-pack.md).
