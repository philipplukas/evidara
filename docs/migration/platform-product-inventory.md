# Platform vs product inventory (Evidara repo)

**Purpose:** tag every deploy-related path as **platform** (cluster-wide / shared enforcement /
namespaces) vs **product** (Evidara workloads, images, app config) vs **hybrid**, and record the
**merge owner** and **credential surface**. Update this table when paths move to MacConfig GitOps.

Legend: **Platform** → candidate for MacConfig `clusters/<env>/…`; **Product** → stays in Evidara
(or future `k8s/` GitOps in this repo); **Hybrid** → split by resource (see notes).

## Kubernetes and data plane

| Path / artifact | Class | Merge owner | Credentials / identity | Notes |
| --- | --- | --- | --- | --- |
| [`infra/terraform/opensearch/gke_stack/main.tf`](../../infra/terraform/opensearch/gke_stack/main.tf) (`google_container_cluster`, node pool, VPC) | Platform | Infra | GCP Terraform SA | GKE cluster lifecycle stays Terraform until you explicitly move to fleet/IaC elsewhere. |
| Same file: `kubernetes_namespace_v1.opensearch` | Hybrid | Infra | GKE / Terraform | Default namespace is `opensearch` (see variables). MacConfig contract [`allowedPattern`](../../vendor/platform-contract.yaml) expects namespaces `evidare-dev`, `evidare-staging`, or `evidare-prod` — align **either** set `opensearch_namespace` to an allowed name (for example `evidare-staging`) **or** negotiate a **minor** MacConfig contract bump for a dedicated OpenSearch namespace pattern. |
| Same file: `helm_release` OpenSearch chart | Product (data plane) | Infra + Search | GKE | Serving dependency for legal-search; long-term may become GitOps-managed Helm in Evidara or a dedicated chart repo. |
| MacConfig `clusters/prod/namespaces/*.yaml` | Platform | Platform / MacConfig | Argo / cluster admin | Source of truth in **MacConfig**; not duplicated in Evidara. |
| MacConfig `clusters/prod/network/*.yaml` | Platform | Platform / MacConfig | Argo / cluster admin | Baseline `NetworkPolicy`. |
| MacConfig `clusters/prod/rbac/*.yaml` | Platform | Platform / MacConfig | Argo / cluster admin | Evidare deployer RBAC template. |

## GCP runtime (no in-repo raw K8s YAML)

| Path / artifact | Class | Merge owner | Credentials / identity | Notes |
| --- | --- | --- | --- | --- |
| [`infra/terraform/gcp/runtime_stack/main.tf`](../../infra/terraform/gcp/runtime_stack/main.tf) (Cloud Run, Pub/Sub, Cloud SQL, buckets, …) | Product | Infra | GCP Terraform SA | Deployed via Terraform + [GitHub Actions CD](../../.github/workflows/); not covered by MacConfig `platform-contract` YAML kinds until you render static manifests. |
| [`.github/workflows/platform-control-cd.yml`](../../.github/workflows/platform-control-cd.yml), [`document-intelligence-cd.yml`](../../.github/workflows/document-intelligence-cd.yml), related | Product | Platform + DI teams | GitHub OIDC → GCP | Image promotion and Cloud Run updates. |

## Contracts and CI (build-time, not cluster)

| Path / artifact | Class | Merge owner | Notes |
| --- | --- | --- | --- |
| [`contracts/`](../../contracts/) | Product (API surface) | Service owners | OpenAPI / JSON Schema; separate from MacConfig platform contract. |
| [`vendor/platform-contract.yaml`](../../vendor/platform-contract.yaml) | Platform (pin) | Platform | Vendored from MacConfig; bump with README pin when MacConfig bumps `contractVersion`. |

## Argo CD

| Path / artifact | Class | Merge owner | Notes |
| --- | --- | --- | --- |
| [`k8s/gitops/{dev,staging,prod}/`](../../k8s/gitops/) | Product | Infra + service teams | Kustomize roots for Argo **product** app; start with **staging** (see [parallel workstreams](parallel-workstreams.md)). |
| Cluster `Application` objects | Platform (orchestration) | Platform | **Not** applied by CI; see [examples](examples/) and [Argo cutover checklist](argo-cutover-checklist.md). |

## “What moved” (fill as you cut over)

| Resource (kind / ns / name) | Old path / repo | New path (MacConfig) | Argo Application (or owner) |
| --- | --- | --- | --- |
| OpenSearch Helm namespace convention | Default `opensearch` in `gke_stack` | N/A (still Terraform Helm) | Examples + validation: use `evidare-<env>` (see `infra/env/*/opensearch.gke.tfvars.example` and `opensearch_namespace` variable validation). |
| Product GitOps Kustomize roots | N/A (new) | [`k8s/gitops/`](../../k8s/gitops/) in Evidara | Argo **product** app `path:` → `k8s/gitops/<env>`; [staging example](examples/product-argocd-application-staging.template.yaml). |
| *TBD* | | | |

## “What intentionally did not move”

| Item | Reason |
| --- | --- |
| Cloud Run Terraform modules | Product deploy path until GitOps migration is scoped. |
| Databricks / DI Terraform | Data plane; not Kubernetes. |
