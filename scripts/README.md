# Scripts

Operator-focused entry points (from repo root unless noted).

| Script | Purpose |
|--------|---------|
| [`e2e-smoke-test.sh`](e2e-smoke-test.sh) | Full pipeline smoke vs Cloud Run (`--env dev\|staging\|prod`). Private Run: set `EVIDARA_GCP_IMPERSONATE_SERVICE_ACCOUNT` or `E2E_PC_ID_TOKEN` / `E2E_LS_ID_TOKEN`. |
| [`mvp-acceptance-scenario-pack.sh`](mvp-acceptance-scenario-pack.sh) | HTTP scenarios 1–4 for dev/staging; same impersonation env as e2e. |
| [`mint-cloud-run-tokens.sh`](mint-cloud-run-tokens.sh) | Prints `export …` lines for `EVIDARA_PLATFORM_CONTROL_TOKEN`, `EVIDARA_LEGAL_SEARCH_TOKEN`, `E2E_PC_ID_TOKEN`, `E2E_LS_ID_TOKEN`. |
| [`smoke-evidara-cli.sh`](smoke-evidara-cli.sh) | Local/API `evidara` pings when `EVIDARA_CLI_SMOKE=1`. |

Auth details: [docs/setup/gcp-local-cloud-run-auth.md](../docs/setup/gcp-local-cloud-run-auth.md) and [docs/runbooks/mvp-acceptance-scenario-pack.md](../docs/runbooks/mvp-acceptance-scenario-pack.md).
