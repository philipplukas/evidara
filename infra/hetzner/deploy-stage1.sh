#!/usr/bin/env bash
# Stage 1 foundation for self-hosted Evidara on Hetzner k3s (ADR-0029):
# namespace + MinIO + CloudNativePG Postgres. Idempotent — safe to re-run.
#
# Usage (from your laptop, with kubeconfig pointing at the cluster):
#   export KUBECONFIG=~/.kube/evidara-hetzner.yaml
#   bash infra/hetzner/deploy-stage1.sh
set -euo pipefail

SCRIPT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
CNPG_VERSION="1.24.0"

echo "==> Checking cluster connectivity"
kubectl get nodes

echo "==> Namespace"
kubectl apply -f "${SCRIPT_DIR}/00-namespace.yaml"

echo "==> MinIO (S3 object storage)"
helm repo add minio https://charts.min.io/ >/dev/null 2>&1 || true
helm repo update minio
helm upgrade --install minio minio/minio -n evidara -f "${SCRIPT_DIR}/values/minio.yaml" --wait --timeout 5m

echo "==> CloudNativePG operator"
kubectl apply --server-side -f \
  "https://raw.githubusercontent.com/cloudnative-pg/cloudnative-pg/release-1.24/releases/cnpg-${CNPG_VERSION}.yaml"
kubectl -n cnpg-system rollout status deploy/cnpg-controller-manager --timeout 5m

echo "==> Postgres cluster"
kubectl apply -f "${SCRIPT_DIR}/postgres-cluster.yaml"
echo "    waiting for the database to be ready..."
kubectl -n evidara wait --for=condition=Ready cluster/evidara-pg --timeout 5m || \
  kubectl -n evidara get cluster evidara-pg

echo
echo "==> Stage 1 status"
kubectl -n evidara get pods
echo
echo "Done. MinIO buckets: evidara-raw-artifacts, evidara-lakehouse."
echo "Postgres RW service: evidara-pg-rw:5432 (db platform_control); creds in secret evidara-pg-app."
