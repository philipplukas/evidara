# Document Intelligence Release Gates

Owner: Platform team
Last reviewed: 2026-04-11
Last verified: 2026-04-11
Applies to: dev, staging, prod

## Scope

This runbook documents the required CI checks that must pass before any
document-intelligence change is merged or deployed. All gates run in both
pre-commit (local) and GitHub Actions (CI).

## Quality Gates (CI + pre-commit)

All gates are exercised by `scripts/check-document-intelligence.sh`.

| Gate | Tool | What it catches |
|------|------|-----------------|
| JSON schema validation | `validate_json_schemas.py` | Broken contract schemas in `contracts/` |
| Lint | `ruff check` | Python code quality issues |
| Format | `ruff format --check` | Code style drift |
| Unit / integration tests | `pytest tests/` | Functional regressions (same as pre-commit / `check-document-intelligence.sh`) |
| OpenAPI contract lint | `@redocly/cli lint` | Invalid OpenAPI specs for DI APIs |
| dbt deps + parse | `dbt parse` | Broken dbt model definitions |

## Runtime Gates (CI only)

| Gate | Tool | What it catches |
|------|------|-----------------|
| DI surface schema preflight (dev smoke) | `scripts/check-di-surface-schema-drift.sh` | Delta surface required-column drift before smoke execution |

Cloud Run calls in `E2E Smoke Dev` use audience-scoped ID tokens minted via
service-account impersonation. This is required for reliable invocation under
GitHub Workload Identity Federation credentials.

## Container Image Build (CI only)

Exercised by `.github/workflows/runtime-images.yml`.

| Gate | What it catches |
|------|-----------------|
| Docker build (consumer) | Broken `Dockerfile` or missing dependencies |

## Release Checklist

Before promoting a document-intelligence change to production:

1. All CI checks pass on the PR (quality + runtime gates)
2. Container image builds successfully
3. DI schema preflight passes in dev (`published_*` surfaces)
4. Smoke-test ingestion flow in dev environment

## Dev Runtime Verification Commands

Run preflight and smoke together:

```bash
cd evidara
PROJECT_ID=project-dacd6b7b-dc96-4534-b82 \
DI_SURFACES_ROOT_URI=gs://evidara-document-intelligence-surfaces-dev/published \
bash scripts/check-di-surface-schema-drift.sh

GCP_PROJECT_ID=project-dacd6b7b-dc96-4534-b82 \
SMOKE_SEED_URL=http://example.org \
SMOKE_REQUEST_TIMEOUT_SECONDS=10 \
scripts/e2e-smoke-test.sh --env dev
```

If preflight fails with a hard drift error in dev, reset surfaces and rerun:

```bash
gcloud storage rm --recursive "gs://evidara-document-intelligence-surfaces-dev/published/**"
```

## Related Files

- [`scripts/check-document-intelligence.sh`](../../scripts/check-document-intelligence.sh)
- [`scripts/check-di-surface-schema-drift.sh`](../../scripts/check-di-surface-schema-drift.sh)
- [`.github/workflows/document-intelligence.yml`](../../.github/workflows/document-intelligence.yml)
- [`.github/workflows/runtime-images.yml`](../../.github/workflows/runtime-images.yml)
- [`.github/workflows/e2e-smoke-dev.yml`](../../.github/workflows/e2e-smoke-dev.yml)
