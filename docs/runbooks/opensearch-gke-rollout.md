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
terraform plan -var-file=../../env/<env>/opensearch.gke.tfvars
terraform apply -var-file=../../env/<env>/opensearch.gke.tfvars
```

2. Sync OpenSearch endpoint and credentials into Secret Manager:

```bash
python3 scripts/sync_opensearch_secrets.py \
  --project-id <project-id> \
  --env <env> \
  --opensearch-stack-dir infra/terraform/opensearch/gke_stack
```

3. Update runtime Cloud Run services to use the VPC connector output (`vpc_connector_id`) in `runtime.gcp.tfvars` (`vpc_connector`, `vpc_egress`), then apply runtime stack.

4. Roll runtime services and verify they can connect to OpenSearch.

## Validation gates

Run these before promoting from `dev` to `staging` and `prod`.

1. Terraform checks:

```bash
terraform fmt -check -recursive infra/terraform
terraform -chdir=infra/terraform/opensearch/gke_stack validate
terraform -chdir=infra/terraform/gcp/runtime_stack validate
```

2. Endpoint/auth/alias check:

```bash
python3 scripts/verify_opensearch_runtime.py \
  --endpoint "$(gcloud secrets versions access latest --secret=opensearch-node-<env> --project=<project-id>)" \
  --username "$(gcloud secrets versions access latest --secret=opensearch-username-<env> --project=<project-id>)" \
  --password "$(gcloud secrets versions access latest --secret=opensearch-password-<env> --project=<project-id>)"
```

3. Application validation:
- Run legal-search projection replay against the new endpoint.
- Run alias cutover script in `legal-search/api/scripts/opensearch-alias-cutover.ts`.
- Verify search and detail API responses against expected documents.

## Rotation and recovery

- Rotate credentials by adding new Secret Manager versions, then rolling Cloud Run revisions.
- If OpenSearch service degrades, keep aliases pointing at previous healthy indices while repairing cluster state.
- Rebuild indices from DI published surfaces if corruption is detected; OpenSearch remains a rebuildable serving layer.
