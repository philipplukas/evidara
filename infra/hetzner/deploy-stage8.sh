#!/usr/bin/env bash
# Stage 8 for self-hosted Evidara on Hetzner k3s: Zitadel, the OIDC identity
# provider (ADR-0038 §2, sequenced as §8 step 2). Idempotent.
#
# What this does NOT do: wire any application to Zitadel. ADR-0038 §8 orders
# steps 3-7 (operator schema, the assertion seam, Auth.js on admin, roles,
# Auth.js on legal-search) strictly after this one, because §8 step 2 requires
# standing it up to be *boring* before anything depends on it. Nothing in this
# repo talks to Zitadel after you run this script; that is the intended state.
#
# Prereqs:
#   1. Stage 1 (MinIO + CNPG `evidara-pg`) is up and healthy.
#   2. DNS A record: id.evidara.veyo.dev -> 88.99.26.120 (see auth/ingress-tls.yaml
#      for the same prereq on admin./search.). Wait until it resolves — cert-manager
#      solves HTTP-01 over Traefik and will fail loudly otherwise.
#   3. Backups: `postgres-cluster.yaml` already archives the WHOLE instance, so the
#      `zitadel` database joins the existing path with no new config (#793). Read
#      docs/runbooks/zitadel-identity-provider.md first — the offsite-destination
#      gate there is a real prerequisite before real user credentials land in it.
#
# Usage (laptop, KUBECONFIG pointed at the cluster):
#   bash infra/hetzner/deploy-stage8.sh
set -euo pipefail

SCRIPT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
NS=evidara
PG_POD=evidara-pg-1
CHART_VERSION=10.0.4   # app v4.15.3 — pin it; an IdP is not a "latest" dependency

echo "==> Checking cluster connectivity"
kubectl get nodes >/dev/null
kubectl -n "$NS" get cluster evidara-pg >/dev/null

# --- 1. Database credential -------------------------------------------------
# Zitadel gets its OWN Postgres role, not platform_control's. Nessie shares the
# platform_control owner (postgres-cluster.yaml), and this deliberately does not:
# an IdP is the highest-value target in the runtime (ADR-0038 §2b), and a leak of
# its DSN must not also hand over every run, approval and operator row.
#
# Create-once, like evidara-auth in deploy-stage5.sh: a re-run must never mint a
# new password over a working instance. The DSN is the single source of truth for
# the password, so it is read back out of the Secret to re-assert the role.
echo "==> Postgres credential for Zitadel (created once; re-runs preserve it)"
if kubectl -n "$NS" get secret zitadel-db >/dev/null 2>&1; then
  echo "    reusing existing zitadel-db Secret"
  ZITADEL_DSN="$(kubectl -n "$NS" get secret zitadel-db \
    -o jsonpath='{.data.ZITADEL_DATABASE_POSTGRES_DSN}' | base64 -d)"
  ZITADEL_PW="$(printf '%s' "$ZITADEL_DSN" | sed -E 's#^postgresql://zitadel:([^@]+)@.*#\1#')"
  if [[ -z "$ZITADEL_PW" || "$ZITADEL_PW" == "$ZITADEL_DSN" ]]; then
    echo "ERROR: could not parse the password out of the existing zitadel-db DSN." >&2
    echo "       Refusing to guess. Inspect the Secret and fix it by hand." >&2
    exit 1
  fi
else
  # hex only: no shell/URL/SQL quoting hazards anywhere downstream.
  ZITADEL_PW="$(openssl rand -hex 24)"
  ZITADEL_DSN="postgresql://zitadel:${ZITADEL_PW}@evidara-pg-rw.${NS}.svc:5432/zitadel?sslmode=disable"
  kubectl -n "$NS" create secret generic zitadel-db \
    --from-literal=ZITADEL_DATABASE_POSTGRES_DSN="$ZITADEL_DSN"
  echo "    generated zitadel-db (DSN never printed)"
fi

# --- 2. Role + database in the existing CNPG cluster ------------------------
# Same precedent as Nessie (postgres-cluster.yaml): the database is created
# post-bootstrap against the running instance, not by CNPG's initdb.
#
# Zitadel is configured in DSN mode, and its own docs are explicit that "in DSN
# mode, zitadel init cannot use the Admin connection to create a separate target
# database/user" — so the role and database MUST exist before the chart's init
# job runs. That is what this block is for, and why initJob.command is `zitadel`.
echo "==> Role 'zitadel' and database 'zitadel' in evidara-pg"
kubectl -n "$NS" exec -i "$PG_POD" -c postgres -- \
  psql -U postgres -v ON_ERROR_STOP=1 -q <<SQL
DO \$\$
BEGIN
  IF NOT EXISTS (SELECT FROM pg_roles WHERE rolname = 'zitadel') THEN
    CREATE ROLE zitadel LOGIN;
  END IF;
END
\$\$;
ALTER ROLE zitadel WITH LOGIN PASSWORD '${ZITADEL_PW}';
SQL
echo "    role 'zitadel' present, password matches the Secret"

if kubectl -n "$NS" exec "$PG_POD" -c postgres -- \
     psql -U postgres -tAc "SELECT 1 FROM pg_database WHERE datname = 'zitadel';" \
     | grep -q 1; then
  echo "    database 'zitadel' already exists (ok)"
else
  kubectl -n "$NS" exec "$PG_POD" -c postgres -- \
    psql -U postgres -v ON_ERROR_STOP=1 -c "CREATE DATABASE zitadel OWNER zitadel;"
  echo "    created database 'zitadel' owned by role 'zitadel'"
fi

# --- 3. Masterkey -----------------------------------------------------------
# 32 bytes, printable ASCII. This encrypts every private key and token Zitadel
# stores: a database backup WITHOUT this key restores to an unusable instance.
# Created once and never rotated by this script — see the runbook.
echo "==> Zitadel masterkey (created once; re-runs preserve it)"
if kubectl -n "$NS" get secret zitadel-masterkey >/dev/null 2>&1; then
  echo "    reusing existing zitadel-masterkey"
else
  # `openssl rand -hex 16` is exactly 32 ASCII bytes. Deliberately not
  # `tr -dc ... </dev/urandom | head -c 32`: under `set -o pipefail` that SIGPIPEs
  # and fails the script intermittently.
  kubectl -n "$NS" create secret generic zitadel-masterkey \
    --from-literal=masterkey="$(openssl rand -hex 16)"
  echo "    generated zitadel-masterkey"
  echo "    !! BACK THIS UP OUT-OF-BAND NOW — see the runbook's break-glass section."
fi

unset ZITADEL_PW ZITADEL_DSN

# --- 4. The chart -----------------------------------------------------------
echo "==> Zitadel (chart ${CHART_VERSION})"
helm repo add zitadel https://charts.zitadel.com >/dev/null 2>&1 || true
helm repo update zitadel
helm upgrade --install zitadel zitadel/zitadel \
  --version "$CHART_VERSION" \
  -n "$NS" \
  -f "${SCRIPT_DIR}/values/zitadel.yaml" \
  --wait --timeout 10m

echo
echo "==> Stage 8 status"
kubectl -n "$NS" get pods -l app.kubernetes.io/instance=zitadel
kubectl -n "$NS" get ingress zitadel zitadel-login
kubectl -n "$NS" get certificate id-evidara-tls 2>/dev/null || \
  echo "    (no Certificate yet — cert-manager may still be solving HTTP-01)"

echo
echo "Done. Verify, in this order:"
echo "  1. curl -sS https://id.evidara.veyo.dev/debug/healthz    # 200, trusted cert"
echo "  2. curl -sS https://id.evidara.veyo.dev/.well-known/openid-configuration | jq .issuer"
echo "     -> must be exactly https://id.evidara.veyo.dev"
echo "  3. open https://id.evidara.veyo.dev/ui/console            # login UI renders"
echo
echo "Initial IAM admin credentials (created by the chart's setup job):"
echo "  kubectl -n ${NS} get secret iam-admin -o jsonpath='{.data.iam-admin\\.json}' | base64 -d"
echo "  kubectl -n ${NS} get secret iam-admin-pat -o jsonpath='{.data.pat}' | base64 -d"
echo "  The human admin's generated password is printed by the setup job:"
echo "  kubectl -n ${NS} logs job/zitadel-setup | grep -i password"
echo
echo "Then run the restore drill in docs/runbooks/zitadel-identity-provider.md."
echo "ADR-0038 §8 step 2 is not done until that drill has passed once."
