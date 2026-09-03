#!/usr/bin/env bash
# Assert that each MinIO service account can reach exactly the buckets it needs and
# nothing else (#813). This is the part that makes the scoping *real* rather than
# asserted: a policy document proves nothing until a denied call is observed denied.
#
# Generalises the two deny checks ADR-0038 §2 introduced for `cnpg-backup`:
#
#   cnpg-backup -> evidara-pg-backups/      OK
#   cnpg-backup -> evidara-raw-artifacts/   Access Denied
#
# The matrix comes from minio-policies/accounts.json, so adding an account or widening
# a policy without widening its expectations fails here rather than in production.
#
# ---------------------------------------------------------------------------------
# WHY THE PROBE OBJECTS ARE SEEDED BY ROOT FIRST
#
# The first version of this script asserted "read is denied" by running `mc cat` against
# a key that did not exist. A missing object returns NoSuchKey whether or not
# `s3:GetObject` is granted, so `expect=deny` matched unconditionally: every read
# assertion passed by construction and could never fail. Granting `s3:GetObject` on
# `evidara-raw-artifacts/*` to `platform-control` — the internet-facing webhook ingester,
# which is supposed to be write-only — would still have printed PASS.
#
# So before testing, root writes one `.evidara-read-probe` object per bucket-and-prefix
# the matrix reads from, and removes them afterwards. A denied read is then a *permission*
# result, not an absence. The write probe is a separate key (`.evidara-write-probe`) so a
# write test can never clobber a read probe, and it is always placed INSIDE the account's
# granted prefix — probing the bucket root for a `canonical/`-scoped account was the
# second way this could pass vacuously.
# ---------------------------------------------------------------------------------
#
# Checks performed per account per bucket, in this order:
#   list   `mc ls`   — allow/deny per the account's allow/deny lists
#   read   `mc cat`  — against the root-seeded probe; allow for `ro`/`rw`, DENY for `wo`
#                      and for every denied bucket
#   write  `mc pipe` — put a probe inside the granted prefix, then remove it; allow for
#                      `wo`/`rw`, DENY for `ro` and for every denied bucket. `pipe`
#                      streams a PutObject rather than stat-ing the destination first,
#                      which matters for the write-only `platform-control` account: a
#                      client that HEADs before writing would report a false deny.
#
# Read-only and write-only accounts are asserted as such: `document-service` must not be
# able to write the canonical surfaces, and `platform-control` must not be able to read
# raw artifacts back (it only stores and purges them — see the table in README.md).
#
# Usage (laptop, KUBECONFIG pointed at the cluster):
#   bash infra/hetzner/verify-minio-scoping.sh            # every account
#   bash infra/hetzner/verify-minio-scoping.sh trino      # one or more accounts
#
# Reports every violation, then exits non-zero if there was one.
set -euo pipefail

SCRIPT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
NS="${NS:-evidara}"
ACCOUNTS_JSON="${SCRIPT_DIR}/minio-policies/accounts.json"
MC_CONFIG_DIR="/tmp/evidara-mcverify-$$"

command -v kubectl >/dev/null || { echo "kubectl not on PATH"; exit 1; }
command -v python3 >/dev/null || { echo "python3 not on PATH"; exit 1; }
[ -f "$ACCOUNTS_JSON" ] || { echo "missing $ACCOUNTS_JSON"; exit 1; }

WANTED=("$@")

POD="$(kubectl -n "$NS" get pod -l app=minio -o jsonpath='{.items[0].metadata.name}')"
[ -n "$POD" ] || { echo "no MinIO pod in namespace $NS"; exit 1; }

# Root is used ONLY to place and remove the read probes — never to test an account.
ROOT_USER="$(kubectl -n "$NS" get secret minio-root -o jsonpath='{.data.rootUser}' | base64 -d)"
ROOT_PW="$(kubectl -n "$NS" get secret minio-root -o jsonpath='{.data.rootPassword}' | base64 -d)"
: "${ROOT_USER:?Secret minio-root not found (infra/hetzner/README.md, Stage 1)}"
: "${ROOT_PW:?Secret minio-root has no rootPassword key}"

# `bucket:key` pairs, deduplicated — the read probes root must place before testing.
SEED_SPECS="$(python3 "${SCRIPT_DIR}/minio-policies/scoping_matrix.py" --seeds "$ACCOUNTS_JSON")"
# user \t k8s_secret \t access_key_field \t secret_key_field \t "bucket:check:expect:key ..."
# `:` and not `|` as the field separator: the check list is interpolated unquoted into
# the `for spec in ...` line of the in-pod script, and a bare `|` there is a shell pipe.
# Bucket names, check names and probe keys contain no `:`.
MATRIX_TSV="$(python3 "${SCRIPT_DIR}/minio-policies/scoping_matrix.py" --matrix "$ACCOUNTS_JSON")"

SEEDED=0
cleanup() {
  if [ "$SEEDED" -eq 1 ]; then
    kubectl -n "$NS" exec -i "$POD" -- sh -s >/dev/null 2>&1 <<EOSH || true
mc --config-dir ${MC_CONFIG_DIR} alias set root "http://localhost:9000" '${ROOT_USER}' '${ROOT_PW}' >/dev/null 2>&1
for spec in ${SEED_SPECS}; do
  OLDIFS="\$IFS"; IFS=':'; set -- \$spec; IFS="\$OLDIFS"
  mc --config-dir ${MC_CONFIG_DIR} rm "root/\$1/\$2" >/dev/null 2>&1 || true
done
EOSH
  fi
  kubectl -n "$NS" exec "$POD" -- rm -rf "$MC_CONFIG_DIR" >/dev/null 2>&1 || true
}
trap cleanup EXIT

echo "==> Seeding read probes as root (removed again on exit)"
SEEDED=1
kubectl -n "$NS" exec -i "$POD" -- sh -s <<EOSH
set -eu
mc --config-dir ${MC_CONFIG_DIR} alias set root "http://localhost:9000" '${ROOT_USER}' '${ROOT_PW}' >/dev/null
for spec in ${SEED_SPECS}; do
  OLDIFS="\$IFS"; IFS=':'; set -- \$spec; IFS="\$OLDIFS"
  echo evidara-scoping-read-probe | mc --config-dir ${MC_CONFIG_DIR} pipe "root/\$1/\$2" >/dev/null
done
EOSH

wanted() {
  [ ${#WANTED[@]} -eq 0 ] && return 0
  for w in "${WANTED[@]}"; do
    [ "$w" = "$1" ] && return 0
  done
  return 1
}

FAILURES=0
CHECKED=0
while IFS=$'\t' read -r USER_NAME K8S_SECRET AK_FIELD SK_FIELD CHECKS; do
  [ -n "$USER_NAME" ] || continue
  wanted "$USER_NAME" || continue

  AK="$(kubectl -n "$NS" get secret "$K8S_SECRET" -o "jsonpath={.data.${AK_FIELD}}" 2>/dev/null | base64 -d 2>/dev/null || true)"
  SK="$(kubectl -n "$NS" get secret "$K8S_SECRET" -o "jsonpath={.data.${SK_FIELD}}" 2>/dev/null | base64 -d 2>/dev/null || true)"
  if [ -z "$AK" ] || [ -z "$SK" ]; then
    echo "==> ${USER_NAME}: FAIL — Secret ${K8S_SECRET} missing ${AK_FIELD}/${SK_FIELD}"
    echo "    run: bash ${SCRIPT_DIR}/provision-minio-users.sh ${USER_NAME}"
    FAILURES=$((FAILURES + 1))
    continue
  fi

  echo "==> ${USER_NAME} (via Secret ${K8S_SECRET})"
  if kubectl -n "$NS" exec -i "$POD" -- sh -s <<EOSH
set -u
CFG=${MC_CONFIG_DIR}
mc --config-dir "\$CFG" alias set u "http://localhost:9000" '${AK}' '${SK}' >/dev/null 2>&1 || {
  echo "    FAIL alias set — credential in ${K8S_SECRET} is not accepted by MinIO"
  exit 1
}
fail=0
for spec in ${CHECKS}; do
  OLDIFS="\$IFS"; IFS=':'; set -- \$spec; IFS="\$OLDIFS"
  bucket=\$1; check=\$2; expect=\$3; key=\$4
  case "\$check" in
    list)
      if mc --config-dir "\$CFG" ls "u/\$bucket/" >/dev/null 2>&1; then got=allow; else got=deny; fi
      ;;
    read)
      # The key exists — root seeded it — so a failure here is a permission result.
      if mc --config-dir "\$CFG" cat "u/\$bucket/\$key" >/dev/null 2>&1; then got=allow; else got=deny; fi
      ;;
    write)
      if echo evidara-scoping-write-probe | mc --config-dir "\$CFG" pipe "u/\$bucket/\$key" >/dev/null 2>&1; then
        got=allow
        mc --config-dir "\$CFG" rm "u/\$bucket/\$key" >/dev/null 2>&1 || true
      else
        got=deny
      fi
      ;;
    *) echo "    FAIL unknown check \$check"; fail=1; continue ;;
  esac
  if [ "\$got" = "\$expect" ]; then
    echo "    PASS \$bucket \$check(\$key) -> \$expect"
  else
    echo "    FAIL \$bucket \$check(\$key) -> expected \$expect, got \$got"
    fail=1
  fi
done
exit \$fail
EOSH
  then
    CHECKED=$((CHECKED + 1))
  else
    FAILURES=$((FAILURES + 1))
  fi
done <<< "$MATRIX_TSV"

echo
if [ "$FAILURES" -ne 0 ]; then
  echo "FAIL: ${FAILURES} account(s) are not scoped as declared in minio-policies/accounts.json"
  exit 1
fi
if [ "$CHECKED" -eq 0 ]; then
  echo "No accounts matched ${WANTED[*]:-<all>} — check minio-policies/accounts.json"
  exit 1
fi
echo "OK: ${CHECKED} account(s) reach exactly the buckets, prefixes and operations they are scoped to"
