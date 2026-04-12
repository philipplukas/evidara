# Argo CD examples (templates)

These files are **not** applied by Evidara CI. They are copy-paste starting points for operators
configuring Argo CD in a cluster.

| File | Use |
| --- | --- |
| [`platform-argocd-application.yaml`](platform-argocd-application.yaml) | MacConfig platform `Application` (namespaces, netpol, RBAC). |
| [`product-argocd-application-staging.template.yaml`](product-argocd-application-staging.template.yaml) | Evidara product `Application` for **staging**; path [`k8s/gitops/staging`](../../../k8s/gitops/staging). |
| [`product-argocd-application.template.yaml`](product-argocd-application.template.yaml) | Evidara product `Application` for **prod**; path [`k8s/gitops/prod`](../../../k8s/gitops/prod). |

See [../argo-cutover-checklist.md](../argo-cutover-checklist.md) and [../parallel-workstreams.md](../parallel-workstreams.md).
