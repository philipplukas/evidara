# Evidara CLI remote smoke — GitHub Actions (operator)

Owner: Platform / DevOps  
Last reviewed: 2026-04-08  
Last verified: 2026-04-08  
Applies to: repository **Actions → Evidara CLI remote smoke** (`.github/workflows/evidara-cli-remote-smoke.yml`)

## Purpose

The workflow is **workflow_dispatch only**. It runs `evidara platform-control ping` and `evidara legal-search ping` against **URLs you type** into the form.

**Cloud Run IAM (Bearer):** the workflow authenticates with **Google OIDC** (Workload Identity Federation) as the environment service account (`GCP_SERVICE_ACCOUNT_DEV` or `GCP_SERVICE_ACCOUNT_STAGING`) and then **mints** audience-scoped ID tokens for the two base URLs you enter from the active CI credentials. You do **not** need repository secrets `EVIDARA_PLATFORM_CONTROL_TOKEN` / `EVIDARA_LEGAL_SEARCH_TOKEN` for private Cloud Run in CI.

**Terraform:** manage GitHub environments and secrets with [`infra/terraform/github/repo_settings`](../../infra/terraform/github/repo_settings/README.md) (`environment_secrets` for WIF + SA email; optional `repository_secrets` for API keys — see README warning on short-lived Google ID tokens).

**Local / manual:** for tokens from your laptop, see [MVP acceptance — Cloud Run auth](mvp-acceptance-scenario-pack.md#cloud-run-auth-local-and-cli) and [GCP local Cloud Run auth](../setup/gcp-local-cloud-run-auth.md).

## Steps (GitHub configuration)

1. Ensure **GitHub Environment** `dev` or `staging` has secrets **`GCP_WORKLOAD_IDENTITY_PROVIDER`** and **`GCP_SERVICE_ACCOUNT_DEV`** / **`GCP_SERVICE_ACCOUNT_STAGING`** (typically applied via Terraform — see [`infra/terraform/github/repo_settings/README.md`](../../infra/terraform/github/repo_settings/README.md)).
1. Optional **repository** secrets for app-layer API keys (Terraform: `repository_secrets` / `TF_VAR_repository_secrets`):

| Secret name | Maps to | When to set |
|-------------|---------|-------------|
| `EVIDARA_PLATFORM_CONTROL_API_KEY` | `X-API-Key` on platform-control requests | Deployed API enforces operator key |
| `EVIDARA_LEGAL_SEARCH_API_KEY` | `X-API-Key` on legal-search BFF | BFF expects `X-API-Key` |

Leave a secret **unset** if unused.

1. **Actions** → **Evidara CLI remote smoke** → **Run workflow** → choose **github_environment** (`dev` or `staging`) → enter **platform_control_url** and **legal_search_url** (HTTPS origins for the two Cloud Run services, e.g. `https://platform-control-api-dev-….run.app`).

## Security

- Use **environment-specific** API keys or tokens where possible; rotate on compromise.
- Do not paste secrets into issues, PRs, or chat logs.
- The workflow uses **GitHub Environments** (`dev` / `staging`) for WIF secrets; environment protection rules (required reviewers) apply to each run for the chosen environment.

## Related docs

- Env var reference: [Environment strategy](../setup/environment-strategy.md) (section **Evidara CLI env vars (dev / staging / prod)**)
- CLI usage: [tools/evidara-cli/README.md](../../tools/evidara-cli/README.md)
- Local / CI API smoke matrix: [Evidara CLI environment smoke matrix](evidara-cli-environment-smoke-matrix.md)
