#!/usr/bin/env bash
# Provision one least-privilege MinIO user per workload, and the Kubernetes Secret
# each workload reads it from (#813).
#
# Until this existed, `platform-control-api`, `di-consumer`, `document-service`,
# `projection-bridge` and both Trino pods all authenticated to MinIO as **root** out of
# a single Secret (`evidara-app-secrets`), so a compromise of any one of them reached
# `evidara-raw-artifacts`, `evidara-lakehouse` *and* `evidara-pg-backups` — the backups
# that exist to recover from exactly that. #792 closed the *leak* (the credential was
# committed and live); it deliberately left the blast radius alone.
#
# The pattern here is not new: ADR-0038 step 2 already provisioned a `cnpg-backup` user
# scoped to the backup bucket only, with a deny test. This generalises it, and folds
# `cnpg-backup` itself into the same table so there is one way to do this, not two.
#
# Source of truth for who gets what: minio-policies/accounts.json + the policy documents
# beside it. Nothing is hardcoded here.
#
# Idempotent. Safe to re-run: an account whose Secret already exists keeps its existing
# password (so re-running does not silently rotate credentials out from under running
# pods) and only has its policy re-applied. Passwords are generated in-cluster-side
# shell, never printed, never committed.
#
# Usage (laptop, KUBECONFIG pointed at the cluster):
#   bash infra/hetzner/provision-minio-users.sh              # all accounts
#   bash infra/hetzner/provision-minio-users.sh trino        # one or more accounts
#
# Then assert the scoping actually holds:
#   bash infra/hetzner/verify-minio-scoping.sh
#
# Cutover procedure (which workloads to restart, in which order, and how to roll back):
#   docs/runbooks/minio-least-privilege-cutover.md
set -euo pipefail

SCRIPT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
NS="${NS:-evidara}"
POLICY_DIR="${SCRIPT_DIR}/minio-policies"
ACCOUNTS_JSON="${POLICY_DIR}/accounts.json"
MC_CONFIG_DIR="/tmp/evidara-mccfg-$$"

command -v kubectl >/dev/null || { echo "kubectl not on PATH"; exit 1; }
command -v python3 >/dev/null || { echo "python3 not on PATH"; exit 1; }
[ -f "$ACCOUNTS_JSON" ] || { echo "missing $ACCOUNTS_JSON"; exit 1; }

WANTED=("$@")

echo "==> Checking cluster connectivity"
kubectl get nodes >/dev/null

POD="$(kubectl -n "$NS" get pod -l app=minio -o jsonpath='{.items[0].metadata.name}')"
[ -n "$POD" ] || { echo "no MinIO pod in namespace $NS"; exit 1; }

# Root is used HERE and nowhere else: it is the administrative credential that creates
# the per-workload users. No workload manifest may reference it — that is the whole point
# of this script, and scripts/check_hetzner_minio_credentials.py enforces it on the files.
ROOT_USER="$(kubectl -n "$NS" get secret minio-root -o jsonpath='{.data.rootUser}' | base64 -d)"
ROOT_PW="$(kubectl -n "$NS" get secret minio-root -o jsonpath='{.data.rootPassword}' | base64 -d)"
: "${ROOT_USER:?Secret minio-root not found — provision it first (infra/hetzner/README.md, Stage 1)}"
: "${ROOT_PW:?Secret minio-root has no rootPassword key}"

cleanup() {
  kubectl -n "$NS" exec "$POD" -- rm -rf "$MC_CONFIG_DIR" /tmp/evidara-policy.json >/dev/null 2>&1 || true
}
trap cleanup EXIT

# Buckets first: `mb --ignore-existing` is a no-op for the two the chart creates, and
# creates `evidara-pg-backups`, which no chart owns (ADR-0038 §2).
BUCKETS="$(python3 -c 'import json,sys;print(" ".join(json.load(open(sys.argv[1]))["all_buckets"]))' "$ACCOUNTS_JSON")"
echo "==> Buckets"
kubectl -n "$NS" exec -i "$POD" -- sh -s <<EOSH
set -eu
mc --config-dir ${MC_CONFIG_DIR} alias set root "http://localhost:9000" '${ROOT_USER}' '${ROOT_PW}' >/dev/null
for b in ${BUCKETS}; do
  mc --config-dir ${MC_CONFIG_DIR} mb --ignore-existing "root/\$b" >/dev/null
done
EOSH

ACCOUNTS_TSV="$(python3 - "$ACCOUNTS_JSON" <<'PY'
import json
import sys

data = json.load(open(sys.argv[1], encoding="utf-8"))
for account in data["accounts"]:
    print(
        "\t".join(
            (
                account["user"],
                account["policy_file"],
                account["k8s_secret"],
                account["access_key_field"],
                account["secret_key_field"],
            )
        )
    )
PY
)"

wanted() {
  [ ${#WANTED[@]} -eq 0 ] && return 0
  for w in "${WANTED[@]}"; do
    [ "$w" = "$1" ] && return 0
  done
  return 1
}

PROVISIONED=0
while IFS=$'\t' read -r USER_NAME POLICY_FILE K8S_SECRET AK_FIELD SK_FIELD; do
  [ -n "$USER_NAME" ] || continue
  wanted "$USER_NAME" || continue

  POLICY_PATH="${POLICY_DIR}/${POLICY_FILE}"
  [ -f "$POLICY_PATH" ] || { echo "missing policy document $POLICY_PATH"; exit 1; }
  POLICY_JSON="$(cat "$POLICY_PATH")"

  # Reuse the existing password when the Secret is already there. Re-running this script
  # must not rotate a live credential: the `cnpg-backup` account predates it (ADR-0038)
  # and Postgres backups start failing the moment its Secret and MinIO disagree.
  PASSWORD="$(kubectl -n "$NS" get secret "$K8S_SECRET" -o "jsonpath={.data.${SK_FIELD}}" 2>/dev/null | base64 -d 2>/dev/null || true)"
  if [ -z "$PASSWORD" ]; then
    PASSWORD="$(openssl rand -hex 24)"
    ACTION="created"
  else
    ACTION="reconciled (existing password kept)"
  fi

  echo "==> ${USER_NAME}: policy ${POLICY_FILE} -> Secret ${K8S_SECRET} [${ACTION}]"

  kubectl -n "$NS" exec -i "$POD" -- sh -s <<EOSH
set -eu
mc --config-dir ${MC_CONFIG_DIR} alias set root "http://localhost:9000" '${ROOT_USER}' '${ROOT_PW}' >/dev/null
cat > /tmp/evidara-policy.json <<'EOPOL'
${POLICY_JSON}
EOPOL
mc --config-dir ${MC_CONFIG_DIR} admin policy create root '${USER_NAME}' /tmp/evidara-policy.json >/dev/null
mc --config-dir ${MC_CONFIG_DIR} admin user add root '${USER_NAME}' '${PASSWORD}' >/dev/null
if ! ATTACH_OUT=\$(mc --config-dir ${MC_CONFIG_DIR} admin policy attach root '${USER_NAME}' --user '${USER_NAME}' 2>&1); then
  case "\$ATTACH_OUT" in
    *already*) : ;;
    *) echo "\$ATTACH_OUT" >&2; exit 1 ;;
  esac
fi
rm -f /tmp/evidara-policy.json
EOSH

  kubectl -n "$NS" create secret generic "$K8S_SECRET" \
    --from-literal="${AK_FIELD}=${USER_NAME}" \
    --from-literal="${SK_FIELD}=${PASSWORD}" \
    --dry-run=client -o yaml | kubectl apply -f - >/dev/null
  echo "    Secret ${K8S_SECRET} applied (${AK_FIELD}, ${SK_FIELD})"

  PASSWORD=""
  PROVISIONED=$((PROVISIONED + 1))
done <<< "$ACCOUNTS_TSV"

if [ "$PROVISIONED" -eq 0 ]; then
  echo "No accounts matched ${WANTED[*]:-<all>} — check minio-policies/accounts.json"
  exit 1
fi

echo
echo "==> Provisioned ${PROVISIONED} account(s). Now prove the scoping holds:"
echo "    bash ${SCRIPT_DIR}/verify-minio-scoping.sh"
