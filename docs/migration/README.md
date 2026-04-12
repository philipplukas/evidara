# MacConfig GitOps migration (Evidara)

This section tracks the **strangler migration** from Evidara-only provisioning toward
[MacConfig](https://github.com/philipplukas/MacConfig) owning **platform** Kubernetes
(namespaces, baseline `NetworkPolicy`, RBAC, future operators), while Evidara keeps
**product** delivery (services, images, contracts) until GitOps paths exist.

**Parallel execution map:** [Parallel workstreams (migration)](parallel-workstreams.md) — which
lanes can run at the same time and what to serialize.

Canonical sequence (mirrors MacConfig `docs/migration-map.md`):

1. **Vendor platform contract** — [`../../vendor/platform-contract.yaml`](../../vendor/platform-contract.yaml) + README pin + CI (done).
2. **Inventory** — [Platform vs product inventory](platform-product-inventory.md).
3. **Git hygiene** — [Git reconcile checklist](git-reconcile-checklist.md) before large moves.
4. **Migrate platform manifests** — happens in **MacConfig** (`clusters/<env>/…`); Evidara tracks overlap in the inventory doc.
5. **Argo cutover** — [Argo cutover checklist](argo-cutover-checklist.md) + [examples](examples/).
6. **Slim Evidara** — [Slim Evidara plan](slim-evidara-plan.md) (after GitOps owns the workloads).
7. **Cluster enforcement** — [Cluster enforcement plan](cluster-enforcement-plan.md).
8. **Stability** — [Platform contract changelog](platform-contract-changelog.md) + [`../../service-template/README.md`](../../service-template/README.md).

## What Evidara can do in-repo today

- Keep the vendored contract aligned with MacConfig `main`.
- Maintain the inventory and runbooks here.
- Add **product** Kubernetes manifests under an agreed path (for example `service-template/` seeds a layout) before wiring an Argo *application* repo path.

## What still requires operator / second-repo actions

- Applying or editing **Argo CD** `Application` objects in the cluster (not stored in this repo today).
- Editing **MacConfig** for new platform YAML, Kyverno policies, or Argo project rules.
- **Terraform** state moves when OpenSearch-on-GKE stops being Helm-applied from Terraform.

**Internal agent / OpenHands GitOps** should live in a **separate repository** (not Evidara, not
MacConfig product YAML): a small `agent-platform`-style repo with its own `k8s/overlays/` and Argo
*product* app, while MacConfig keeps cluster platform. A scaffold exists next to this monorepo at
`../agent-platform` on disk until you create the GitHub remote and push.


Start with [platform-product-inventory.md](platform-product-inventory.md) and [git-reconcile-checklist.md](git-reconcile-checklist.md).
