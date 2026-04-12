# Product GitOps (Kubernetes)

This tree holds **product** manifests intended for Argo CD `Application` objects (see
[`../../docs/migration/examples/`](../../docs/migration/examples/) and
[`../../docs/migration/parallel-workstreams.md`](../../docs/migration/parallel-workstreams.md)).

## Layout

| Path | Use |
| --- | --- |
| [`dev/`](dev/) | Dev slice: includes a **placeholder `ConfigMap`** for first Argo sync; replace with real workloads. |
| [`staging/`](staging/) | **Preferred first** environment for real manifests before prod (also ships a placeholder `ConfigMap`). |
| [`prod/`](prod/) | Prod slice: **empty** `resources` until staging Argo path is proven. |

**dev** and **staging** use `namespace: evidare-*` in `kustomization.yaml` so rendered objects target
contract-allowed namespaces. Add `Deployment`, `Service`, and other allowed kinds per
[`../../vendor/platform-contract.yaml`](../../vendor/platform-contract.yaml) as you cut over from
Terraform-only delivery. CI renders all trees with `kubectl kustomize` (`scripts/validate_k8s_gitops_kustomize.sh`).
