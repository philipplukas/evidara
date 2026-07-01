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

echo "==> Auth secret: operator key + legal-search key (each created once, reused after)"
if ! kubectl -n "$NS" get secret evidara-auth >/dev/null 2>&1; then
  kubectl -n "$NS" create secret generic evidara-auth \
    --from-literal=PLATFORM_CONTROL_OPERATOR_API_KEY="$(openssl rand -hex 24)" \
    --from-literal=LEGAL_SEARCH_API_KEY="$(openssl rand -hex 24)"
  echo "    generated operator + legal-search API keys"
else
  # Secret exists — add any missing key without disturbing existing values.
  for key in PLATFORM_CONTROL_OPERATOR_API_KEY LEGAL_SEARCH_API_KEY; do
    if kubectl -n "$NS" get secret evidara-auth -o "jsonpath={.data.$key}" | grep -q .; then
      echo "    reusing existing $key"
    else
      kubectl -n "$NS" patch secret evidara-auth --type merge \
        -p "{\"data\":{\"$key\":\"$(printf '%s' "$(openssl rand -hex 24)" | base64)\"}}"
      echo "    added missing $key"
    fi
  done
fi

echo "==> BasicAuth front-door secret (created once; re-runs preserve it)"
# Create-once, like evidara-auth: a re-run must NOT clobber a password that was
# rotated out-of-band. BASIC_AUTH_USER/PASS are only needed for first-time setup.
# To change the password later, rotate the secret directly (htpasswd -nbB | kubectl).
if kubectl -n "$NS" get secret evidara-basicauth >/dev/null 2>&1; then
  echo "    reusing existing evidara-basicauth (password preserved)"
else
  : "${BASIC_AUTH_USER:?Set BASIC_AUTH_USER (front-door login user) for first-time setup}"
  : "${BASIC_AUTH_PASS:?Set BASIC_AUTH_PASS (front-door login password) for first-time setup}"
  if command -v htpasswd >/dev/null 2>&1; then
    HTPASSWD_LINE="$(htpasswd -nbB "$BASIC_AUTH_USER" "$BASIC_AUTH_PASS")"
  else
    HTPASSWD_LINE="${BASIC_AUTH_USER}:$(openssl passwd -apr1 "$BASIC_AUTH_PASS")"
  fi
  kubectl -n "$NS" create secret generic evidara-basicauth --from-literal=users="$HTPASSWD_LINE"
  echo "    created evidara-basicauth for user '${BASIC_AUTH_USER}'"
fi

echo "==> Traefik middleware + ingress"
kubectl apply -f "${SCRIPT_DIR}/auth/basicauth-middleware.yaml"
kubectl apply -f "${SCRIPT_DIR}/auth/ingress.yaml"

echo "==> Re-apply apps (operator + legal-search keys, imagePullPolicy) and restart"
kubectl apply -k "${SCRIPT_DIR}/apps"
kubectl -n "$NS" rollout restart \
  deploy/platform-control-api deploy/platform-control-admin \
  deploy/legal-search-api deploy/legal-search-frontend
kubectl -n "$NS" rollout status deploy/platform-control-admin --timeout 3m
kubectl -n "$NS" rollout status deploy/legal-search-frontend --timeout 3m

echo
echo "Done. Front door (BasicAuth: user '${BASIC_AUTH_USER:-<existing>}' / your password):"
echo "  Admin:  https://admin.88-99-26-120.nip.io"
echo "  Search: https://search.88-99-26-120.nip.io"
echo "(Traefik serves a self-signed cert for now -> click through the browser warning."
echo " Swap to cert-manager + Let's Encrypt + a real domain for trusted TLS.)"
