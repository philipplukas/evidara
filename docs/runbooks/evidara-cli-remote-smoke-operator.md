# Evidara CLI remote smoke — GitHub Actions secrets (operator)

Owner: Platform / DevOps  
Applies to: repository **Actions → Evidara CLI remote smoke** (`.github/workflows/evidara-cli-remote-smoke.yml`)

## Purpose

The workflow is **workflow_dispatch only**. It runs `evidara platform-control ping` and `evidara legal-search ping` against **URLs you type** into the form. Optional **repository secrets** supply auth headers when dev/staging/prod APIs are not anonymous.

Secrets cannot be created from git; configure them once in GitHub.

## Steps (repository secrets)

1. Open the repo on GitHub → **Settings** → **Secrets and variables** → **Actions**.
2. Under **Repository secrets**, **New repository secret** for each value you need (names are **exact**):

| Secret name | Maps to | When to set |
|-------------|---------|-------------|
| `EVIDARA_PLATFORM_CONTROL_API_KEY` | `X-API-Key` on platform-control requests | Platform-control requires API key |
| `EVIDARA_LEGAL_SEARCH_TOKEN` | `Authorization: Bearer …` on legal-search BFF | BFF expects a bearer token |
| `EVIDARA_LEGAL_SEARCH_API_KEY` | `X-API-Key` on legal-search BFF | BFF expects `X-API-Key` instead of/in addition to bearer |

3. Leave a secret **unset** if that auth mechanism is not used (empty env in the workflow).
4. **Actions** → **Evidara CLI remote smoke** → **Run workflow** → enter **platform_control_url** and **legal_search_url** (base URLs only, no path suffix).

## Security

- Use **environment-specific** API keys or tokens where possible; rotate on compromise.
- Do not paste secrets into issues, PRs, or chat logs.
- Prefer **GitHub Environments** with protection rules if you later split staging vs prod secrets (workflow would need a small change to target an `environment:`).

## Related docs

- Env var reference: [Environment strategy](../setup/environment-strategy.md) (section **Evidara CLI env vars (dev / staging / prod)**)
- CLI usage: [tools/evidara-cli/README.md](../../tools/evidara-cli/README.md)
- Local / CI API smoke matrix: [Evidara CLI environment smoke matrix](evidara-cli-environment-smoke-matrix.md)
