# Slim Evidara plan (after GitOps owns workloads)

**Do not delete Terraform or Helm from Evidara until the replacement path is live** in Argo CD
(or another agreed GitOps controller) and traffic has been validated.

## Phase A — documentation only (safe now)

- Keep [platform-product-inventory.md](platform-product-inventory.md) accurate.
- Add product manifests under a single repo path (see [`../../service-template/README.md`](../../service-template/README.md)) **before** removing Terraform equivalents.

## Phase B — OpenSearch on GKE (hybrid)

**Today:** `infra/terraform/opensearch/gke_stack` provisions GKE + namespace + Helm OpenSearch.

**Target:** one of:

1. **Helm stays Terraform, platform-only YAML moves to MacConfig** — minimal slimming; only remove
   duplicated namespace/netpol if Terraform stops managing them; or
2. **Helm moves to Argo** — Terraform retains GKE + networking; Argo syncs a Helm/Kustomize chart for
   OpenSearch; then delete `helm_release` from Terraform in a planned state migration.

Checklist per option:

- [ ] No duplicate `Namespace` for the same name (MacConfig vs Terraform).
- [ ] `terraform plan` is clean after removing resources Argo now owns.
- [ ] Runbook updated: [`../runbooks/runtime-stack.md`](../runbooks/runtime-stack.md) or OpenSearch-specific doc.

## Phase C — Cloud Run / GCP runtime

Terraform in `infra/terraform/gcp/runtime_stack` is still the **product** deploy path for Cloud Run
unless you introduce rendered manifests + Argo (unusual for Cloud Run). “Slim Evidara” here means
**narrowing** Terraform to resources that are not duplicated in GitOps, not deleting Cloud Run
modules without a replacement.

## Phase D — CI scope (optional)

When most cluster YAML leaves the monorepo:

- Restrict workflows to **allowed directories** + contract checks (align with MacConfig
  `docs/platform-boundary.md` when published). Track as a separate ADR or infra ticket.
