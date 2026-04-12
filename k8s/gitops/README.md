# Product GitOps (Kubernetes)

This tree holds **product** manifests intended for an Argo CD `Application` (see
[`../../docs/migration/examples/product-argocd-application.template.yaml`](../../docs/migration/examples/product-argocd-application.template.yaml)).

`prod/kustomization.yaml` starts empty so the path exists and Argo can sync without pruning
unexpected resources; add `Deployment`, `Service`, and other allowed kinds per
[`../../vendor/platform-contract.yaml`](../../vendor/platform-contract.yaml) as you cut over from
Terraform-only delivery.
