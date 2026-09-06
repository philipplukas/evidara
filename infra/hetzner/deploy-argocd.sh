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
# REPOSITORY CREDENTIAL: `philipplukas/evidara` is PRIVATE, so Argo CD cannot read
# it without one. Without the credential the Application reports
# `ComparisonError: ... authentication required` and sync status `Unknown` — note
# that health still shows `Healthy`, so a glance at the wrong column reads as
# working. (Observed on first install, 2026-09-06.)
#
# Supply a token once, out of band:
#
#   ARGOCD_REPO_TOKEN=<token> bash infra/hetzner/deploy-argocd.sh
#
# Use a fine-grained PAT scoped to this repository with **Contents: read-only** —
# not a classic `repo` token, and not a personal OAuth token from `gh auth token`,
# which carries the full scope of your account into the cluster for a job that
# needs to read one repository.
#
# The Secret is created once and preserved on re-runs (same pattern as the
# Grafana admin password in deploy-observability.sh), so routine re-runs need no
# token in the environment.
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

echo "==> Repository credential (created once; re-runs preserve it)"
if kubectl -n "$NS" get secret evidara-repo >/dev/null 2>&1; then
  echo "    reusing existing evidara-repo"
elif [ -n "${ARGOCD_REPO_TOKEN:-}" ]; then
  # `--type` and the argocd.argoproj.io/secret-type label are what make Argo CD
  # pick this up as a repository credential rather than an inert Secret.
  kubectl -n "$NS" create secret generic evidara-repo \
    --from-literal=type=git \
    --from-literal=url=https://github.com/philipplukas/evidara.git \
    --from-literal=username=git \
    --from-literal=password="$ARGOCD_REPO_TOKEN"
  kubectl -n "$NS" label secret evidara-repo argocd.argoproj.io/secret-type=repository
  echo "    created evidara-repo"
else
  echo "!! No 'evidara-repo' Secret and no ARGOCD_REPO_TOKEN in the environment."
  echo "!! The repository is private; without a credential the Application reports"
  echo "!! 'authentication required' and never syncs — while still showing Healthy."
  echo "!! Re-run as: ARGOCD_REPO_TOKEN=<fine-grained PAT, Contents: read> bash $0"
  exit 1
fi

echo "==> Application: evidara-apps"
kubectl apply -f "${SCRIPT_DIR}/argocd/application-evidara-apps.yaml"

echo "==> Waiting for the first comparison"
# A repo credential fault surfaces here as sync status Unknown with a
# ComparisonError condition. Report it rather than printing success over it.
for _ in $(seq 1 30); do
  sync_status="$(kubectl -n "$NS" get application evidara-apps -o jsonpath='{.status.sync.status}' 2>/dev/null || true)"
  [ -n "$sync_status" ] && [ "$sync_status" != "Unknown" ] && break
  sleep 5
done
if [ "${sync_status:-Unknown}" = "Unknown" ]; then
  echo "!! Application sync status is still Unknown. Conditions:"
  kubectl -n "$NS" get application evidara-apps \
    -o jsonpath='{range .status.conditions[*]}    {.type}: {.message}{"\n"}{end}' || true
  echo "!! NOTE: health may read 'Healthy' regardless — that column says nothing"
  echo "!! about whether Argo could read the repository."
  exit 1
fi
echo "    sync status: ${sync_status}"

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
