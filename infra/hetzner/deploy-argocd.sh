#!/usr/bin/env bash
# Argo CD for the self-hosted Evidara cluster (ADR-0055). Idempotent.
#
# Installs the controller and registers ONE Application: `infra/hetzner/apps` →
# the `evidara` namespace. After this, merging a change to
# `infra/hetzner/apps/kustomization.yaml` is what rolls production; a cluster that
# disagrees with `main` shows as OutOfSync instead of being discoverable only by
# asking the cluster. Production sat 35 commits stale, then 27, because nothing
# reconciled (#879, #883).
#
# Usage (laptop, KUBECONFIG pointed at the cluster):
#   bash infra/hetzner/deploy-argocd.sh
#
# PRECONDITION: `deploy-stage4.sh` must have run at least once. It creates the
# `evidara` namespace and the imperative Secrets (evidara-app-secrets, ghcr-pull)
# that Argo CD does NOT manage and that every workload needs at startup. The
# Application sets `CreateNamespace=false` for exactly this reason — a namespace
# Argo creates would be an empty one, and the pods would fail at their first
# secret read rather than at sync.
#
# The repository is public, so no repo credential is registered. If it is ever
# made private, add one with:
#   argocd repo add https://github.com/philipplukas/evidara.git --username … --password …
set -euo pipefail

SCRIPT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
NS=argocd
CHART_VERSION="7.7.11"

echo "==> Checking cluster connectivity"
kubectl get nodes >/dev/null

echo "==> Precondition: the evidara namespace and its imperative Secrets exist"
# Fail fast and say which step is missing, rather than syncing workloads that
# will CrashLoop on a Secret nobody created.
missing=0
kubectl get namespace evidara >/dev/null 2>&1 || { echo "!! namespace 'evidara' not found"; missing=1; }
for secret in evidara-app-secrets ghcr-pull; do
  kubectl -n evidara get secret "$secret" >/dev/null 2>&1 || {
    echo "!! secret 'evidara/${secret}' not found"
    missing=1
  }
done
if [ "$missing" -ne 0 ]; then
  echo "!! Run 'bash ${SCRIPT_DIR}/deploy-stage4.sh' first (ADR-0055 precondition)."
  exit 1
fi

echo "==> Namespace ${NS}"
kubectl create namespace "$NS" --dry-run=client -o yaml | kubectl apply -f -

echo "==> Argo CD (helm, chart ${CHART_VERSION})"
helm repo add argo https://argoproj.github.io/argo-helm >/dev/null 2>&1 || true
helm repo update argo >/dev/null
helm upgrade --install argocd argo/argo-cd \
  --namespace "$NS" \
  --version "$CHART_VERSION" \
  -f "${SCRIPT_DIR}/values/argocd.yaml" \
  --wait --timeout 10m

echo "==> Application: evidara-apps"
kubectl apply -f "${SCRIPT_DIR}/argocd/application-evidara-apps.yaml"

echo
echo "Argo CD is installed."
echo "  UI:       https://argocd.ts.veyo.dev   (tailnet only)"
echo "  User:     admin"
echo "  Password: kubectl -n ${NS} get secret argocd-initial-admin-secret \\"
echo "              -o jsonpath='{.data.password}' | base64 -d; echo"
echo
echo "Sync state:"
echo "  kubectl -n ${NS} get application evidara-apps \\"
echo "    -o custom-columns=SYNC:.status.sync.status,HEALTH:.status.health.status"
echo
echo "NOTE: prune is OFF (ADR-0055). The evidara namespace holds Helm- and"
echo "CNPG-owned resources Argo does not manage; enable prune only after"
echo "Application ownership has been confirmed correct."
