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
# The credential is a repository-scoped, READ-ONLY GitHub deploy key. Not a PAT:
# a deploy key has no account behind it, cannot reach any other repository, and
# has no expiry to rotate. GitHub has no API for minting a fine-grained PAT, so a
# PAT would also have to be created by hand in a browser.
#
# The private key lives in 1Password and is read at deploy time — it is never
# committed, never echoed, and never stored on disk:
#
#   op://Infrastructure/evidara-argocd-repo/private_key
#
# so the normal invocation needs no secret in the environment at all:
#
#   bash infra/hetzner/deploy-argocd.sh
#
# `ARGOCD_REPO_SSH_KEY` overrides the 1Password read for a machine without `op`
# (CI, a recovery shell). The Secret is created once and preserved on re-runs
# (same pattern as the Grafana admin password in deploy-observability.sh).
#
# To rotate: delete the deploy key on GitHub, delete the `evidara-repo` Secret,
# generate a new keypair, update the 1Password item, re-run this script.
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
# This URL must match the Application's `repoURL` EXACTLY. Argo CD matches the
# credential to the repository by string, so a mismatch does not error — it
# silently falls back to anonymous access, which for a private repo fails as
# `authentication required` while health still reads `Healthy`.
REPO_SSH_URL="git@github.com:philipplukas/evidara.git"

if kubectl -n "$NS" get secret evidara-repo >/dev/null 2>&1; then
  echo "    reusing existing evidara-repo"
else
  ssh_key="${ARGOCD_REPO_SSH_KEY:-}"
  if [ -z "$ssh_key" ]; then
    if ! command -v op >/dev/null 2>&1; then
      echo "!! No 'evidara-repo' Secret, no ARGOCD_REPO_SSH_KEY, and the 1Password"
      echo "!! CLI ('op') is not installed, so the deploy key cannot be read from"
      echo "!! op://Infrastructure/evidara-argocd-repo/private_key."
      exit 1
    fi
    echo "    reading the deploy key from 1Password"
    # Read straight into a variable: the key never lands on disk, and command
    # substitution keeps it out of the process table (unlike passing it as an arg).
    if ! ssh_key="$(op read "op://Infrastructure/evidara-argocd-repo/private_key" 2>/dev/null)"; then
      echo "!! Could not read op://Infrastructure/evidara-argocd-repo/private_key"
      echo "!! Sign in first:  eval \$(op signin)"
      exit 1
    fi
  fi

  if [ -z "$ssh_key" ]; then
    echo "!! The deploy key resolved to an empty value; refusing to create an"
    echo "!! unusable credential that would fail as 'authentication required'."
    exit 1
  fi

  # An OpenSSH private key must end with a newline or ssh rejects it as malformed.
  # `op read` and $(...) both strip trailing newlines, so it has to be put back —
  # without this the Secret looks correct and every fetch fails.
  kubectl -n "$NS" create secret generic evidara-repo \
    --from-literal=type=git \
    --from-literal=url="$REPO_SSH_URL" \
    --from-file=sshPrivateKey=/dev/stdin <<EOF_KEY
${ssh_key}
EOF_KEY
  # The label is what makes Argo CD treat this as a repository credential rather
  # than an inert Secret.
  kubectl -n "$NS" label secret evidara-repo argocd.argoproj.io/secret-type=repository
  unset ssh_key
  echo "    created evidara-repo from the read-only deploy key"
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
