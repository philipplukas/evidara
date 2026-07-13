#!/usr/bin/env bash
# Observability for self-hosted Evidara on Hetzner k3s (ADR-0032):
# kube-prometheus-stack (Prometheus + Alertmanager + Grafana) into `monitoring`, then the
# Evidara scrape targets, alerts, and the pipeline funnel dashboard. Idempotent.
#
# Answers the question liveness probes cannot: "is work actually flowing?" Every failure
# in the June/July outage (#549/#550/#551) ran green on /health the whole time.
#
# Usage (laptop, KUBECONFIG pointed at the cluster):
#   bash infra/hetzner/deploy-observability.sh
#
# Grafana admin password: generated once into the `evidara-grafana-admin` Secret and
# preserved on re-runs (same create-once pattern as `evidara-auth` in stage 5). Read it
# back with the command printed at the end.
set -euo pipefail

SCRIPT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
NS=monitoring

echo "==> Checking cluster connectivity"
kubectl get nodes >/dev/null

echo "==> Namespace ${NS}"
kubectl create namespace "$NS" --dry-run=client -o yaml | kubectl apply -f -

echo "==> Grafana admin secret (created once; re-runs preserve it)"
if kubectl -n "$NS" get secret evidara-grafana-admin >/dev/null 2>&1; then
  echo "    reusing existing evidara-grafana-admin (password preserved)"
else
  kubectl -n "$NS" create secret generic evidara-grafana-admin \
    --from-literal=admin-user=admin \
    --from-literal=admin-password="$(openssl rand -hex 24)"
  echo "    generated a Grafana admin password"
fi

echo "==> kube-prometheus-stack (Prometheus + Alertmanager + Grafana)"
helm repo add prometheus-community https://prometheus-community.github.io/helm-charts >/dev/null 2>&1 || true
helm repo update prometheus-community
helm upgrade --install kube-prometheus-stack prometheus-community/kube-prometheus-stack \
  -n "$NS" -f "${SCRIPT_DIR}/values/kube-prometheus-stack.yaml" --wait --timeout 10m

echo "==> NATS JetStream exporter (adds the prom-metrics sidecar; no-op if already on)"
helm repo add nats https://nats-io.github.io/k8s/helm/charts/ >/dev/null 2>&1 || true
helm repo update nats
helm upgrade --install nats nats/nats -n evidara -f "${SCRIPT_DIR}/values/nats.yaml" --wait --timeout 5m

echo "==> Evidara scrape targets, alerts, funnel dashboard"
# Applied after the Helm release: these are Prometheus Operator CRs, and the CRDs only
# exist once the chart is installed.
kubectl apply -k "${SCRIPT_DIR}/observability"

echo
echo "==> Status"
kubectl -n "$NS" get pods
echo
echo "==> Scrape targets (expect legal-search-api, platform-control-api, di-consumer,"
echo "    projection-bridge, nats — each with a /metrics endpoint)"
kubectl -n evidara get servicemonitor,podmonitor
echo
echo "Done."
echo
echo "Grafana — the pipeline funnel is the dashboard that matters:"
echo "  kubectl -n $NS port-forward svc/kps-grafana 3000:80   # -> http://localhost:3000"
echo "  user: admin"
echo "  pass: kubectl -n $NS get secret evidara-grafana-admin -o jsonpath='{.data.admin-password}' | base64 -d; echo"
echo
echo "Prometheus / Alertmanager:"
echo "  kubectl -n $NS port-forward svc/kps-prometheus 9090:9090"
echo "  kubectl -n $NS port-forward svc/kps-alertmanager 9093:9093"
echo
echo "!! First-rollout check — confirm the NATS JetStream metric names resolve, or the"
echo "   JetStream alerts are decorative (see docs/setup/hetzner-observability.md):"
echo "     kubectl -n $NS exec sts/prometheus-kps-prometheus -c prometheus -- \\"
echo "       wget -qO- 'http://localhost:9090/api/v1/query?query=jetstream_consumer_num_pending'"
