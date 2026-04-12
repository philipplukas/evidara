# Argo CD cutover checklist (platform vs product)

Evidara does **not** commit live Argo `Application` objects today. Use this checklist when you
register Applications in the cluster (or in a small GitOps “apps of apps” repo).

## Preconditions

- [MacConfig `clusters/prod` kustomization](https://github.com/philipplukas/MacConfig/tree/main/clusters/prod)
  applies cleanly in a non-prod cluster (or dry-run equivalent).
- [Platform vs product inventory](platform-product-inventory.md) lists no duplicate `kind/ns/name`
  ownership between MacConfig and Evidara paths.
- Vendored [`vendor/platform-contract.yaml`](../../vendor/platform-contract.yaml) matches MacConfig `main`.

## Two-application model (recommended)

| Application | `spec.source.repoURL` | `spec.source.path` | Purpose |
| --- | --- | --- | --- |
| **platform** | MacConfig | `clusters/<env>` | Namespaces, baseline netpol, RBAC, future operators. |
| **product** | Evidara (this monorepo) | *TBD* — e.g. `k8s/gitops/<env>` once created | Deployments, Services, Ingress, `ExternalSecret`, HPA, PDB for Evidara workloads only. |

## Steps

1. **Create Argo CD `AppProject` boundaries** (cluster): restrict **product** project to allowed
   namespaces and resource kinds per the vendored contract.
2. **Apply platform Application** using [platform example](examples/platform-argocd-application.yaml)
   (edit `repoURL`, `project`, labels).
3. **Wait for sync**; confirm namespaces and baseline RBAC/NetworkPolicy exist.
4. **Prepare product manifests** in Evidara (start from [`../../service-template/README.md`](../../service-template/README.md)).
5. **Apply product Application** from [product template](examples/product-argocd-application.template.yaml).
6. **Validate no duplicate ownership** — same `kind` + `namespace` + `name` must not be synced by
   both Applications unless one is `ServerSideApply` owner (avoid).
7. **Cut traffic / DNS** only after product sync is healthy (runbook per environment).

## Rollback

- Disable auto-sync on the **product** Application first.
- Re-enable Terraform / Cloud Run–only path if that was the previous source of truth for workloads.

## References

- MacConfig upstream example: `clusters/prod/examples/platform-argocd-application.yaml`
- [Cluster enforcement plan](cluster-enforcement-plan.md) for Kyverno / RBAC hardening after cutover.
