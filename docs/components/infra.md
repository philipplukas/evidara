# Infrastructure

## Purpose

Provision and document runtime and deployment environments for all Evidara components.

## Current state

Repository structure exists with Terraform directory layout. No Terraform modules or cloud resources are defined yet. Environment strategy (dev/staging/prod) is documented as planned but not configured.

## Source of truth

- `infra/terraform/` for all infrastructure definitions
- `infra/env/` for per-environment configuration
- Terraform state (remote) for actual provisioned resources

## Structure

```text
infra/
  terraform/
    gcp/         # Google Cloud resources
    databricks/  # Databricks workspace and resources
    github/      # GitHub repository automation
  env/
    dev/         # Development environment config
    staging/     # Staging environment config
    prod/        # Production environment config
```

## Minimal next tasks

- [ ] Define target GCP services and resource names
- [ ] Define target Databricks resources
- [ ] Define Terraform module structure
- [ ] Define environment strategy (dev/staging/prod)
- [ ] Define naming conventions for cloud resources
- [ ] Define secrets strategy (Google Secret Manager)
- [ ] Document infrastructure overview (`docs/setup/infrastructure-overview.md`)
- [ ] Document environment strategy (`docs/setup/environment-strategy.md`)

## Minimal v1 Outcome

The repo can provision:

1. A basic GCS bucket layout (raw artifacts, processed outputs)
2. A Cloud SQL (Postgres) instance for platform-control
3. Basic Cloud Run service definitions
4. Minimal Pub/Sub topics
5. Databricks-connected storage paths

## Later expansion

| Phase | Capability |
|-------|-----------|
| Next | CI/CD deployment workflows |
| Next | Environment protection rules |
| Later | Monitoring and alerting |
| Later | Service accounts and IAM tightening |
| Later | Reindex pipeline infrastructure |

## Dependencies

| Dependency | Purpose |
|-----------|---------|
| GCP | Cloud provider for all runtime services |
| Databricks | Processing and Delta storage provider |
| Terraform | Infrastructure as code tooling |
| GitHub Actions | CI/CD orchestration |

## Cloud Services

| Service | Provider | Purpose |
|---------|----------|---------|
| Cloud Run | GCP | Application runtime (platform-control, legal-search) |
| Cloud SQL | GCP | Postgres for platform-control |
| Cloud Storage | GCP | Raw artifact storage |
| Pub/Sub | GCP | Event messaging |
| Databricks | Databricks | Document intelligence processing and Delta storage |
| OpenSearch | Managed | Search serving (provider TBD) |

## Principles

- **No secrets in Git.** All credentials use managed secret stores.
- **Infrastructure as Code.** All provisioning through Terraform.
- **Environment parity.** Dev, staging, and prod use the same Terraform modules with different variables.

## Testing

See [Infra Testing](testing/infra-testing.md) for the full testing strategy.

Key tests:

- `terraform fmt -check` on all `.tf` files
- `terraform validate` on all modules
- Basic plan generation
- Environment config sanity checks
- Naming convention checks
- Documentation consistency with actual Terraform structure

## Drift risks

| Risk | Mitigation |
|------|-----------|
| Actual infrastructure drifts from Terraform definitions | `terraform plan` comparison (later: automated) |
| Environment configs diverge | Shared modules with per-env variables |
| Naming conventions become inconsistent | Naming convention checker |
| Infra docs become stale | Doc consistency checks |
| Secrets accidentally committed | `detect-private-key` pre-commit hook |
