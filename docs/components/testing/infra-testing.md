# Infra Testing

## Scope

Testing strategy for the infra component, which owns:

- Terraform configurations
- Environment config (dev, staging, prod)
- Cloud resource definitions (GCP)
- Deployment assumptions
- IAM / secrets assumptions (where documented)

---

## Minimal Tests for MVP

### Terraform Formatting

- Run `terraform fmt -check` on all `.tf` files
- Enforce consistent formatting in CI
- This is fast, deterministic, and catches sloppy changes

### Terraform Validation

- Run `terraform validate` on all modules
- Catches syntax errors, unknown providers, invalid references
- Does not require credentials or state

### Basic Plan Generation

- Run `terraform plan` with a test variable file
- Verify the plan generates without errors
- Do not assert on specific resources — just verify the plan succeeds
- Requires credentials (run in CI with a service account, or locally)

### Module-Level Validation

For each Terraform module:

- Module can be initialized (`terraform init`)
- Module validates without errors
- Module has required variables documented

### Environment Config Sanity Checks

- Each environment directory (dev, staging, prod) has required files
- Variable values are consistent across environments where expected (e.g., naming conventions)
- No hardcoded secrets in config files

### Naming Convention Checks

- Resource names follow Evidara naming conventions
- Labels and tags are consistent
- Project IDs and region values are correct

### Documentation Consistency

- `docs/components/infra.md` describes the same resources defined in Terraform
- Major resources in Terraform have corresponding documentation
- This can be a manual checklist initially, automated later

---

## Recommended Later Tests

### Policy Checks

- Use a tool like `tfsec`, `checkov`, or `opa` to enforce security policies
- Examples: no public buckets, IAM roles follow least privilege, encryption enabled

### Drift Detection (Infra)

- Compare `terraform plan` output against expected state
- Detect when actual infrastructure has drifted from Terraform definitions
- Run nightly or weekly

### Deployment Smoke Tests

- After deployment, verify that key services are reachable
- Cloud Run services respond to health checks
- Cloud SQL is accessible from expected networks
- Pub/Sub topics exist and are subscribable
- GCS buckets exist and are accessible

### Service Readiness Checks

- After deployment, verify that services are fully initialized
- Database migrations have run
- Search index is available
- Event subscriptions are active

---

## Confidence Goal

These tests should answer:

- **Can infra be validated before deployment?** — Format, validate, and plan checks catch errors before they reach production.
- **Can the team safely evolve infra with minimal surprises?** — Naming checks, doc consistency, and later policy checks prevent configuration drift.

---

## Important: Keep Infra Testing Lightweight Initially

Infra testing for a small team should focus on:

1. **Structure and safety** — is the Terraform valid and well-formatted?
2. **Reviewability** — can someone understand what will change from a plan?
3. **Documentation consistency** — do the docs match the infra?

Do **not** attempt full production simulation in CI. That requires dedicated infrastructure, is slow, and is fragile. Add it only when the team has the bandwidth to maintain it.

---

## What NOT to Overbuild Early

- Do not build a full staging environment clone for testing
- Do not build automated infra drift remediation
- Do not build complex policy-as-code suites before the infra stabilizes
- Do not test IAM permissions exhaustively — validate the structure, trust the documentation for now

---

## Later Expansion

| Phase | Addition |
|-------|---------|
| Post-MVP | Security policy checks (tfsec/checkov) |
| Post-MVP | Deployment smoke tests |
| Later | Infra drift detection (plan vs actual) |
| Later | Cost monitoring and alerting |
| Later | Multi-environment promotion testing |
