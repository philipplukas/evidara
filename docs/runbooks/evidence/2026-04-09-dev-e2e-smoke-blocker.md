# Dev e2e smoke — not executed (2026-04-09)

**Linear:** TAR-64 (evidence gap until a privileged environment runs the script twice).

## What was attempted

```bash
./scripts/e2e-smoke-test.sh --env dev
```

with default `GCP_PROJECT_ID=data-platform-dev-492214`.

## Blocker

`gcloud run services describe` fails: **Cloud Run Admin API disabled** (or no access) on that project for the active account. Non-interactive check:

```text
ERROR: (gcloud.run.services.describe) PERMISSION_DENIED: Cloud Run Admin API has not been used in project data-platform-dev-492214 before or it is disabled.
```

An earlier run also stalled on an interactive **“Enable API and retry?”** prompt when prompts were not disabled.

## Next step for operators

1. Use a project where **Cloud Run Admin API** is enabled and you have **run.services.get** (or run the official **GitHub Actions** e2e workflow with OIDC + impersonation, per [m5-evidence-checklist.md](../m5-evidence-checklist.md)).
2. Run `./scripts/e2e-smoke-test.sh --env dev` **twice**; attach logs or Actions URLs to **TAR-64**.
