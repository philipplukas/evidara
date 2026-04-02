# Security Policy

## Reporting Vulnerabilities

If you discover a security vulnerability in Evidara, please report it responsibly:

1. **Do not** open a public issue.
2. Contact the repository owner directly via a private channel.
3. Include a clear description of the vulnerability, steps to reproduce, and potential impact.

We will acknowledge receipt within 48 hours and provide an expected timeline for a fix.

## Credential and Secret Handling

### Rules

- **Never commit secrets** to this repository. This includes API keys, database passwords, service account keys, tokens, and certificates.
- **Credentials live only in managed secret stores.** In production, secrets are managed through cloud-native secret management (e.g., Google Secret Manager).
- **No raw internal credentials in docs or examples.** Use placeholder values like `<YOUR_API_KEY>` or `${SECRET_NAME}` in documentation and configuration examples.
- **Environment files are gitignored.** Files like `.env`, `.env.local`, and `.env.*.local` must never be committed.

### What To Do If You Accidentally Commit a Secret

1. **Rotate the credential immediately.** Assume it is compromised.
2. Remove the secret from Git history (use `git filter-branch` or BFG Repo-Cleaner).
3. Force push the cleaned history.
4. Notify the team.

## Dependency Security

- Keep dependencies up to date.
- Review dependency changes in pull requests.
- Use automated tools (e.g., Dependabot, Snyk) when available.
