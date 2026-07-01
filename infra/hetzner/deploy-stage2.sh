#!/usr/bin/env bash
# Stage 2 for self-hosted Evidara on Hetzner k3s (ADR-0029):
# NATS JetStream (+ EVIDARA stream) and OpenSearch. Idempotent.
#
# Usage (laptop, KUBECONFIG pointed at the cluster):
#   bash infra/hetzner/deploy-stage2.sh
set -euo pipefail

SCRIPT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"

echo "==> Checking cluster connectivity"
kubectl get nodes

echo "==> NATS JetStream"
helm repo add nats https://nats-io.github.io/k8s/helm/charts/ >/dev/null 2>&1 || true
helm repo update nats
helm upgrade --install nats nats/nats -n evidara -f "${SCRIPT_DIR}/values/nats.yaml" --wait --timeout 5m

echo "==> EVIDARA JetStream stream"
kubectl apply -f "${SCRIPT_DIR}/nats-stream-init.job.yaml"
kubectl -n evidara wait --for=condition=complete job/nats-evidara-stream-init --timeout 2m || \
  kubectl -n evidara logs job/nats-evidara-stream-init --tail=20

echo "==> OpenSearch (single node)"
helm repo add opensearch https://opensearch-project.github.io/helm-charts/ >/dev/null 2>&1 || true
helm repo update opensearch
helm upgrade --install opensearch opensearch/opensearch -n evidara -f "${SCRIPT_DIR}/values/opensearch.yaml" --wait --timeout 10m

echo
echo "==> Stage 2 status"
kubectl -n evidara get pods
echo
echo "Done."
echo "  NATS:       nats://nats.evidara.svc:4222   (stream EVIDARA, subjects evidara.>)"
echo "  OpenSearch: http://opensearch-cluster-master.evidara.svc:9200"
