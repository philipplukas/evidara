# Document Intelligence Release Gates

Owner: Platform team
Last reviewed: 2026-04-03
Last verified: 2026-04-03
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
| Unit tests | `unittest discover` | Functional regressions |
| OpenAPI contract lint | `@redocly/cli lint` | Invalid OpenAPI specs for DI APIs |
| dbt deps + parse | `dbt parse` | Broken dbt model definitions |

## Runtime / Deployment Gates (CI only)

Exercised by `scripts/check-document-intelligence-runtime.sh` in the
`document-intelligence-runtime-check` CI job.

| Gate | Tool | What it catches |
|------|------|-----------------|
| Terraform fmt | `terraform fmt -check` | Inconsistent HCL formatting |
| Terraform validate | `terraform validate` | Invalid Terraform config for DI modules |

## Container Image Build (CI only)

Exercised by `.github/workflows/runtime-images.yml`.

| Gate | What it catches |
|------|-----------------|
| Docker build (consumer) | Broken `Dockerfile` or missing dependencies |

## CD Pipeline Gates

Exercised by `.github/workflows/document-intelligence-cd.yml` on push to
`main`.

| Gate | Tool | What it catches |
|------|------|-----------------|
| DAB validate (dev) | `databricks bundle validate` | Invalid bundle config |
| DAB deploy (dev) | `databricks bundle deploy` | Failed deployment to dev |
| DAB validate (prod) | `databricks bundle validate` | Invalid prod bundle config |
| DAB deploy (prod) | `databricks bundle deploy` | Failed deployment to prod |

## Release Checklist

Before promoting a document-intelligence change to production:

1. All CI checks pass on the PR (quality + runtime gates)
2. Container image builds successfully
3. DAB dev deployment succeeds
4. DAB prod deployment succeeds (requires manual approval via GitHub environment)
5. Smoke-test ingestion flow in dev environment

## Related Files

- [`scripts/check-document-intelligence.sh`](../../scripts/check-document-intelligence.sh)
- [`scripts/check-document-intelligence-runtime.sh`](../../scripts/check-document-intelligence-runtime.sh)
- [`.github/workflows/document-intelligence.yml`](../../.github/workflows/document-intelligence.yml)
- [`.github/workflows/document-intelligence-cd.yml`](../../.github/workflows/document-intelligence-cd.yml)
- [`.github/workflows/runtime-images.yml`](../../.github/workflows/runtime-images.yml)
