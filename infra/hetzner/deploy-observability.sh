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

echo "==> Alert receivers (evidara-alertmanager Secret)"
# Holds the Telegram bot token, mounted into Alertmanager as a file
# so they never appear in git or in `helm get values`. Created out-of-band:
#   docs/setup/hetzner-observability.md#wiring-the-receivers
#
# `chat_id` is the one value Alertmanager will not read from a file — it must be an
# inline int64 — so we read it back out of the Secret and substitute it at render
# time. It is not a credential (it is inert without the bot token), but keeping it
# beside the token means there is exactly one place to configure.
if kubectl -n "$NS" get secret evidara-alertmanager >/dev/null 2>&1; then
  EVIDARA_TELEGRAM_CHAT_ID="$(kubectl -n "$NS" get secret evidara-alertmanager \
    -o jsonpath='{.data.telegram-chat-id}' | base64 -d)"
  if [[ -z "${EVIDARA_TELEGRAM_CHAT_ID}" ]]; then
    echo "    error: secret evidara-alertmanager has no telegram-chat-id key." >&2
    echo "    See docs/setup/hetzner-observability.md#wiring-the-receivers." >&2
    exit 1
  fi
  echo "    receivers configured (Telegram: critical pages hourly, warnings every 4h)"
else
  # Deliberately not fatal. A missing Secret must not block the dashboards and the
  # rules engine — but say so loudly, because silent non-delivery is the exact
  # failure this stack exists to catch.
  EVIDARA_TELEGRAM_CHAT_ID=0
  echo "    !! WARNING: secret evidara-alertmanager not found."
  echo "    !! Alerts will fire into the Alertmanager UI and NOWHERE ELSE."
  echo "    !! Nobody's phone will ring. See docs/setup/hetzner-observability.md."
fi
export EVIDARA_TELEGRAM_CHAT_ID

VALUES_RENDERED="$(mktemp)"
trap 'rm -f "$VALUES_RENDERED"' EXIT
# shellcheck disable=SC2016 # envsubst needs the literal name, not its value
envsubst '${EVIDARA_TELEGRAM_CHAT_ID}' \
  < "${SCRIPT_DIR}/values/kube-prometheus-stack.yaml" > "$VALUES_RENDERED"

echo "==> kube-prometheus-stack (Prometheus + Alertmanager + Grafana)"
helm repo add prometheus-community https://prometheus-community.github.io/helm-charts >/dev/null 2>&1 || true
helm repo update prometheus-community
helm upgrade --install kube-prometheus-stack prometheus-community/kube-prometheus-stack \
  -n "$NS" -f "$VALUES_RENDERED" --wait --timeout 10m

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
echo "       wget -qO- 'http://localhost:9090/api/v1/query?query=nats_consumer_num_pending'"
