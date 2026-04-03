# OpenSearch on GKE Rollout Runbook

Owner: Platform team
Last reviewed: 2026-04-03
Last verified: Not yet verified
Applies to: dev, staging, prod

## Scope

This runbook provisions and validates self-managed OpenSearch on GKE with a dedicated VPC for `dev`, `staging`, and `prod`.

## Prerequisites

- `gcloud` authenticated for the target project
- Terraform `>= 1.5`
- Access to write Secret Manager versions in target project
- Runtime container images already pushed to Artifact Registry

## Deploy sequence (per environment)

1. Apply OpenSearch GKE stack:

```bash
cd infra/terraform/opensearch/gke_stack
terraform init
terraform plan -var-file=../../../env/<env>/opensearch.gke.tfvars
terraform apply -var-file=../../../env/<env>/opensearch.gke.tfvars
```

1. Sync OpenSearch endpoint and credentials into Secret Manager:

```bash
python3 scripts/sync_opensearch_secrets.py \
  --project-id <project-id> \
  --env <env> \
  --opensearch-stack-dir infra/terraform/opensearch/gke_stack
```

1. Set runtime private egress assumptions in `infra/env/<env>/runtime.gcp.tfvars`:
   - `runtime_vpc_access_connector` (from OpenSearch stack output `vpc_connector_id`)
   - `runtime_vpc_egress` (`PRIVATE_RANGES_ONLY` recommended)

1. Apply runtime stack and roll services so new secret versions and networking assumptions are active.

## Validation gates

Run these before promoting from `dev` to `staging` and `prod`.

1. Terraform checks:

```bash
terraform fmt -check -recursive infra/terraform
terraform -chdir=infra/terraform/opensearch/gke_stack init -backend=false
terraform -chdir=infra/terraform/opensearch/gke_stack validate
terraform -chdir=infra/terraform/gcp/runtime_stack init -backend=false
terraform -chdir=infra/terraform/gcp/runtime_stack validate
```

1. Endpoint/auth/alias check:

```bash
python3 scripts/verify_opensearch_runtime.py \
  --endpoint "$(gcloud secrets versions access latest --secret=opensearch-node-<env> --project=<project-id>)" \
  --username "$(gcloud secrets versions access latest --secret=opensearch-username-<env> --project=<project-id>)" \
  --password "$(gcloud secrets versions access latest --secret=opensearch-password-<env> --project=<project-id>)"
```

1. Application validation:

   - Run legal-search replay against the new endpoint.
   - Run alias cutover script in `legal-search/api/scripts/opensearch-alias-cutover.ts`.
   - Verify search and detail API responses.

## Rotation and recovery

- Rotate credentials by adding new Secret Manager versions, then roll Cloud Run revisions.
- Keep aliases on previously healthy indices during incident response.
- Rebuild indices from DI published surfaces when needed; OpenSearch is a rebuildable serving layer.
