#!/usr/bin/env bash
# Stage 5 for self-hosted Evidara on Hetzner k3s (ADR-0029 / ADR-0020): real auth.
# - operator API key (Secret) -> platform-control enforces X-API-Key; the admin
#   middleware injects it server-side (rebuild the admin image first).
# - Traefik BasicAuth front door + ingress on nip.io hostnames.
# Idempotent.
#
# Usage (laptop, KUBECONFIG set). Pick a login for the front door:
#   BASIC_AUTH_USER=admin BASIC_AUTH_PASS='choose-a-strong-pass' bash infra/hetzner/deploy-stage5.sh
set -euo pipefail

SCRIPT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
NS=evidara
: "${BASIC_AUTH_USER:?Set BASIC_AUTH_USER (front-door login user)}"
: "${BASIC_AUTH_PASS:?Set BASIC_AUTH_PASS (front-door login password)}"

echo "==> Operator API key (created once, reused after)"
if ! kubectl -n "$NS" get secret evidara-auth >/dev/null 2>&1; then
  kubectl -n "$NS" create secret generic evidara-auth \
    --from-literal=PLATFORM_CONTROL_OPERATOR_API_KEY="$(openssl rand -hex 24)"
  echo "    generated a new operator API key"
else
  echo "    reusing existing operator API key"
fi

echo "==> BasicAuth front-door secret"
if command -v htpasswd >/dev/null 2>&1; then
  HTPASSWD_LINE="$(htpasswd -nbB "$BASIC_AUTH_USER" "$BASIC_AUTH_PASS")"
else
  HTPASSWD_LINE="${BASIC_AUTH_USER}:$(openssl passwd -apr1 "$BASIC_AUTH_PASS")"
fi
kubectl -n "$NS" create secret generic evidara-basicauth \
  --from-literal=users="$HTPASSWD_LINE" --dry-run=client -o yaml | kubectl apply -f -

echo "==> Traefik middleware + ingress"
kubectl apply -f "${SCRIPT_DIR}/auth/basicauth-middleware.yaml"
kubectl apply -f "${SCRIPT_DIR}/auth/ingress.yaml"

echo "==> Re-apply apps (operator key + imagePullPolicy) and restart"
kubectl apply -k "${SCRIPT_DIR}/apps"
kubectl -n "$NS" rollout restart deploy/platform-control-api deploy/platform-control-admin
kubectl -n "$NS" rollout status deploy/platform-control-admin --timeout 3m

echo
echo "Done. Front door (BasicAuth: ${BASIC_AUTH_USER} / your password):"
echo "  Admin:  https://admin.88-99-26-120.nip.io"
echo "  Search: https://search.88-99-26-120.nip.io"
echo "(Traefik serves a self-signed cert for now -> click through the browser warning."
echo " Swap to cert-manager + Let's Encrypt + a real domain for trusted TLS.)"
