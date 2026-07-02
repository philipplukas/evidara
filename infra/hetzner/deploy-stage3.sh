#!/usr/bin/env bash
# Stage 3 for self-hosted Evidara on Hetzner k3s (ADR-0029):
# the lakehouse — Nessie (Iceberg REST catalog) + Trino (query). Idempotent.
#
# Usage (laptop, KUBECONFIG pointed at the cluster):
#   bash infra/hetzner/deploy-stage3.sh
set -euo pipefail

SCRIPT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"

echo "==> Checking cluster connectivity"
kubectl get nodes

echo "==> Nessie database in Postgres"
kubectl -n evidara exec evidara-pg-1 -- \
  psql -c "CREATE DATABASE nessie OWNER platform_control;" 2>/dev/null \
  && echo "    created database 'nessie'" \
  || echo "    database 'nessie' already exists (ok)"

echo "==> Nessie (Iceberg REST catalog)"
helm repo add nessie https://charts.projectnessie.org >/dev/null 2>&1 || true
helm repo update nessie
helm upgrade --install nessie nessie/nessie -n evidara -f "${SCRIPT_DIR}/values/nessie.yaml" --wait --timeout 5m

echo "==> Trino (query engine)"
helm repo add trino https://trinodb.github.io/charts >/dev/null 2>&1 || true
helm repo update trino
helm upgrade --install trino trino/trino -n evidara -f "${SCRIPT_DIR}/values/trino.yaml" --wait --timeout 10m

echo
echo "==> Stage 3 status"
kubectl -n evidara get pods
echo
echo "Done."
echo "  Nessie: http://nessie.evidara.svc:19120/api/v2"
echo "  Trino:  trino.evidara.svc:8080  (catalog 'iceberg')"
echo
echo "Smoke test Trino (port-forward, then query):"
echo "  kubectl -n evidara port-forward svc/trino 8080:8080 &"
echo "  # then with the trino CLI or any client:  SHOW SCHEMAS FROM iceberg;"
