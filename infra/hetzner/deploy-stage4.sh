#!/usr/bin/env bash
# Stage 4 for self-hosted Evidara on Hetzner k3s (ADR-0029): the apps.
# Creates the GHCR pull secret + app secrets, runs DB migrate+seed, deploys the
# services. Idempotent.
#
# Usage (laptop, KUBECONFIG pointed at the cluster):
#   GHCR_TOKEN=<github PAT with read:packages> bash infra/hetzner/deploy-stage4.sh
set -euo pipefail

SCRIPT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
NS=evidara
GHCR_USER="${GHCR_USER:-philipplukas}"
: "${GHCR_TOKEN:?Set GHCR_TOKEN to a GitHub PAT with read:packages scope}"

echo "==> Checking cluster connectivity"
kubectl get nodes >/dev/null

echo "==> GHCR pull secret + default service account"
kubectl -n "$NS" create secret docker-registry ghcr-pull \
  --docker-server=ghcr.io --docker-username="$GHCR_USER" --docker-password="$GHCR_TOKEN" \
  --dry-run=client -o yaml | kubectl apply -f -
kubectl -n "$NS" patch serviceaccount default \
  -p '{"imagePullSecrets":[{"name":"ghcr-pull"}]}'

echo "==> App secrets (DB URL from CNPG password)"
PGPW="$(kubectl -n "$NS" get secret evidara-pg-app -o jsonpath='{.data.password}' | base64 -d)"
# NO MinIO credentials here any more (#813). This Secret is mounted with `envFrom` by
# every platform-control and DI workload, so putting object-storage credentials in it
# handed all of them the same key — and until #813 that key was *root*, which reaches
# `evidara-raw-artifacts`, `evidara-lakehouse` and the `evidara-pg-backups` PITR backups
# alike. #792 stopped the credential being committed; it left that blast radius intact.
#
# Each workload now gets its own scoped MinIO user from its own Secret
# (`evidara-s3-*`), provisioned by infra/hetzner/provision-minio-users.sh and asserted
# by infra/hetzner/verify-minio-scoping.sh. `projection-bridge` gets none at all: it
# makes no object-storage call (it consumes NATS and POSTs HTTP).
#
# Re-running this script removes the old keys from the Secret, because `kubectl apply`
# prunes fields dropped from the previous applied configuration. That is intentional —
# leaving them would keep root live in every pod.
kubectl -n "$NS" create secret generic evidara-app-secrets \
  --from-literal=PLATFORM_CONTROL_DATABASE_URL="postgresql+asyncpg://platform_control:${PGPW}@evidara-pg-rw:5432/platform_control" \
  --dry-run=client -o yaml | kubectl apply -f -

echo "==> Per-workload MinIO credentials"
# Fail before the apps roll rather than after: a workload whose scoped Secret is missing
# starts with no S3 credential and fails at the first artifact write, not at startup.
MISSING_S3_SECRETS=""
for s3_secret in evidara-s3-platform-control evidara-s3-di-consumer evidara-s3-document-service; do
  if ! kubectl -n "$NS" get secret "$s3_secret" >/dev/null 2>&1; then
    MISSING_S3_SECRETS="${MISSING_S3_SECRETS} ${s3_secret}"
  fi
done
if [ -n "$MISSING_S3_SECRETS" ]; then
  echo "!! missing scoped MinIO Secret(s):${MISSING_S3_SECRETS}"
  echo "   run: bash ${SCRIPT_DIR}/provision-minio-users.sh"
  echo "   then: bash ${SCRIPT_DIR}/verify-minio-scoping.sh"
  exit 1
fi

echo "==> Config"
kubectl apply -f "${SCRIPT_DIR}/apps/configmap.yaml"

echo "==> DB migrate + seed"
kubectl -n "$NS" delete job platform-control-migrate --ignore-not-found
kubectl apply -f "${SCRIPT_DIR}/apps/migrate-job.yaml"
if ! kubectl -n "$NS" wait --for=condition=complete job/platform-control-migrate --timeout 5m; then
  echo "!! migrate job did not complete — logs:"
  kubectl -n "$NS" logs job/platform-control-migrate --tail=50 || true
  exit 1
fi

echo "==> Apps"
kubectl apply -k "${SCRIPT_DIR}/apps"

echo
echo "==> Stage 4 status"
kubectl -n "$NS" get pods
echo
echo "Done. Reach the UIs via port-forward (no ingress yet):"
echo "  kubectl -n $NS port-forward svc/legal-search-frontend 3101:8080   # search UI -> http://localhost:3101"
echo "  kubectl -n $NS port-forward svc/platform-control-admin 3100:8080   # admin    -> http://localhost:3100"
