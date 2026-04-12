# Service template (product GitOps)

Placeholder for **future** Kubernetes manifests that Argo CD (or similar) will sync for Evidara
**product** workloads — for example `Deployment`, `Service`, `Ingress`, `ExternalSecret`, `HPA`,
`PDB` in namespaces allowed by [`vendor/platform-contract.yaml`](../vendor/platform-contract.yaml).

## Intended layout (suggestion)

When you add real manifests, prefer a single env-rooted tree so the product Argo Application path
stays stable:

```text
k8s/gitops/<env>/
  kustomization.yaml
  …
```

**dev** and **staging** already include a placeholder `ConfigMap` you can replace.

The [product Argo example](../docs/migration/examples/product-argocd-application.template.yaml) uses
`path: k8s/gitops/prod` as a convention.

## Rules

- Do **not** commit `Namespace`, `ClusterRole`, or other **forbidden** kinds from the vendored
  contract here — those remain **platform** owned in MacConfig.
- Keep namespace names aligned with the contract `allowedPattern` (and resolve OpenSearch
  namespace alignment per [platform-product-inventory.md](../docs/migration/platform-product-inventory.md)).

## See also

- [MacConfig GitOps migration docs](../docs/migration/README.md)
