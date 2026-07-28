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

echo "==> App secrets (DB URL from CNPG password + MinIO creds)"
PGPW="$(kubectl -n "$NS" get secret evidara-pg-app -o jsonpath='{.data.password}' | base64 -d)"
# MinIO creds are read from the `minio-root` Secret, never hardcoded — this script used
# to seed the committed `change-me-minio-root`, which meant re-running it silently
# reinstated the leaked credential after any rotation (#792).
MINIO_USER="$(kubectl -n "$NS" get secret minio-root -o jsonpath='{.data.rootUser}' | base64 -d)"
MINIO_PW="$(kubectl -n "$NS" get secret minio-root -o jsonpath='{.data.rootPassword}' | base64 -d)"
: "${MINIO_USER:?Secret minio-root not found — provision it first (infra/hetzner/README.md)}"
: "${MINIO_PW:?Secret minio-root has no rootPassword key}"
kubectl -n "$NS" create secret generic evidara-app-secrets \
  --from-literal=PLATFORM_CONTROL_DATABASE_URL="postgresql+asyncpg://platform_control:${PGPW}@evidara-pg-rw:5432/platform_control" \
  --from-literal=PLATFORM_CONTROL_S3_ACCESS_KEY_ID="${MINIO_USER}" \
  --from-literal=PLATFORM_CONTROL_S3_SECRET_ACCESS_KEY="${MINIO_PW}" \
  --from-literal=DI_S3_ACCESS_KEY_ID="${MINIO_USER}" \
  --from-literal=DI_S3_SECRET_ACCESS_KEY="${MINIO_PW}" \
  --dry-run=client -o yaml | kubectl apply -f -

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
