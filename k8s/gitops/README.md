# Product GitOps (Kubernetes)

This tree holds **product** manifests intended for Argo CD `Application` objects (see
[`../../docs/migration/examples/`](../../docs/migration/examples/) and
[`../../docs/migration/parallel-workstreams.md`](../../docs/migration/parallel-workstreams.md)).

## Layout

| Path | Use |
| --- | --- |
| [`dev/`](dev/) | Development cluster product slice (empty Kustomize root until you add resources). |
| [`staging/`](staging/) | **Preferred first** environment for real manifests before prod. |
| [`prod/`](prod/) | Production product slice (keep empty until staging Argo path is proven). |

Each `*/kustomization.yaml` starts with `resources: []` so the path exists and Argo can sync
without pruning unexpected resources. Add `Deployment`, `Service`, and other allowed kinds per
[`../../vendor/platform-contract.yaml`](../../vendor/platform-contract.yaml) as you cut over from
Terraform-only delivery.
