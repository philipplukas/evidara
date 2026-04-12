# Cluster enforcement plan (RBAC, Kyverno)

This step is **mostly outside** the Evidara monorepo: policies and cluster-scoped RBAC should live
in [MacConfig](https://github.com/philipplukas/MacConfig) under `clusters/<env>/platform/` (see
MacConfig `clusters/prod/platform/kyverno/README.md`).

## Goals

- Enforce the **machine-readable** rules in [`vendor/platform-contract.yaml`](../../vendor/platform-contract.yaml)
  (allowed kinds, namespace pattern, ingress class, ESO store name).
- Scope deny rules by **caller identity** (Evidara deploy SA vs platform SA), not blanket cluster denial.

## Suggested sequence

1. **AppProject + RBAC** — Argo CD `AppProject` for *product* limits destinations and resource
   whitelists to match `allowedResources` in the contract.
2. **Namespaced Roles** — MacConfig `rbac/` templates; bind to the Evidara CI/deploy service account.
3. **Kyverno `ClusterPolicy`** — add under MacConfig `platform/kyverno/` when API versions and
   schema validation (`kubeconform` / CI) are ready; wire into `kustomization.yaml` only after review.
4. **Proof tasks** — targeted `kubectl` as platform vs as product SA (allow/deny); record commands
   in a runbook.

## Evidara repo responsibilities

- Bump [`vendor/platform-contract.yaml`](../../vendor/platform-contract.yaml) + README pin when
  MacConfig bumps `contractVersion`; document changes in
  [platform-contract-changelog.md](platform-contract-changelog.md).
- Do **not** add `ClusterRole` / `ValidatingWebhookConfiguration` manifests here unless an ADR
  explicitly moves that ownership into the monorepo (conflicts with MacConfig platform ownership).
