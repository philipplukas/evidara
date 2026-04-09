# GCP: local auth for private Cloud Run

Use this checklist once per engineer (or when minting starts failing) before running [`scripts/e2e-smoke-test.sh`](../../scripts/e2e-smoke-test.sh), [`scripts/mvp-acceptance-scenario-pack.sh`](../../scripts/mvp-acceptance-scenario-pack.sh), or [`evidara workflow mvp-acceptance`](../../tools/evidara-cli/README.md) against **dev/staging** APIs.

## 1. Service account (invoker)

- Use the same service account wired for CI e2e (GitHub repository secrets `GCP_SERVICE_ACCOUNT_DEV` / `GCP_SERVICE_ACCOUNT_STAGING`), **or** any SA that has **`roles/run.invoker`** on:
  - `platform-control-api-{env}`
  - `legal-search-api-{env}`
- Confirm in GCP Console: **Cloud Run** → service → **Permissions** → principal includes that SA with **Cloud Run Invoker**.

## 2. Your user (token creator)

- Your Google account needs **`roles/iam.serviceAccountTokenCreator`** on that service account (IAM → service account → **Permissions** → grant your user or group).
- Org policy must allow impersonation; if denied, use an org-approved path (e.g. break-glass SA, or run smokes only from CI).

## 3. gcloud

- `gcloud auth login` with the account that holds **Token Creator** on the SA.
- Optional: `gcloud config set project <project-id>` for `gcloud run services describe` in e2e smoke.

## 4. Repo workflows

| Goal | Mechanism |
|------|-----------|
| Shell checks with impersonation | `export EVIDARA_GCP_IMPERSONATE_SERVICE_ACCOUNT='sa@project.iam.gserviceaccount.com'` then run the scripts (see script headers). |
| CLI Bearer tokens | [`scripts/mint-cloud-run-tokens.sh`](../../scripts/mint-cloud-run-tokens.sh) → sets `EVIDARA_PLATFORM_CONTROL_TOKEN`, `EVIDARA_LEGAL_SEARCH_TOKEN`, and optional `E2E_*` for smoke. |
| Full MVP acceptance | [MVP acceptance scenario pack](../runbooks/mvp-acceptance-scenario-pack.md) — **Cloud Run auth** section. |
| CI reference | [`.github/workflows/e2e-smoke-dev.yml`](../../.github/workflows/e2e-smoke-dev.yml), [`e2e-smoke-staging.yml`](../../.github/workflows/e2e-smoke-staging.yml) (`--impersonate-service-account` + `--audiences`). |

## 5. Env vars (summary)

See [Environment strategy](environment-strategy.md) — **Evidara CLI env vars** and the paragraph on **`EVIDARA_GCP_IMPERSONATE_SERVICE_ACCOUNT`**.
