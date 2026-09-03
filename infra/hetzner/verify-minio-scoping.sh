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
# Checks performed per account per bucket:
#   list   `mc ls`   — expected allow/deny from the account's allow/deny lists
#   read   `mc cat`  — asserted only where it must be DENIED (a permitted read of an
#                      absent key returns NoSuchKey, which is not a permission signal)
#   write  `mc pipe` — put a tiny probe object, then remove it again; on deny-buckets
#                      nothing is ever written. `pipe` streams a PutObject rather than
#                      stat-ing the destination first, which matters for the write-only
#                      `platform-control` account: a client that HEADs before writing
#                      would report a false deny.
#
# Read-only and write-only accounts are asserted as such: `document-service` must not be
# able to write to the lakehouse, and `platform-control` must not be able to *read* raw
# artifacts back (it only stores and purges them — see the table in README.md).
#
# Usage (laptop, KUBECONFIG pointed at the cluster):
#   bash infra/hetzner/verify-minio-scoping.sh            # every account
#   bash infra/hetzner/verify-minio-scoping.sh trino      # one or more accounts
#
# Exits non-zero on the first account with a violation, after reporting all of them.
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

cleanup() {
  kubectl -n "$NS" exec "$POD" -- rm -rf "$MC_CONFIG_DIR" >/dev/null 2>&1 || true
}
trap cleanup EXIT

# user \t k8s_secret \t access_key_field \t secret_key_field \t "bucket:check:expect:key ..."
# `:` and not `|` as the field separator: the check list is interpolated unquoted into the
# `for spec in ...` line of the in-pod script, and a bare `|` there is a shell pipe.
# Bucket names, check names and probe keys contain no `:`.
MATRIX_TSV="$(python3 - "$ACCOUNTS_JSON" <<'PY'
import json
import sys

ABSENT_KEY = ".evidara-scoping-probe-absent"
data = json.load(open(sys.argv[1], encoding="utf-8"))
buckets = data["all_buckets"]

for account in data["accounts"]:
    allowed = {entry["bucket"]: entry for entry in account["allow"]}
    denied = set(account["deny"])
    covered = set(allowed) | denied
    if covered != set(buckets):
        missing = sorted(set(buckets) - covered)
        raise SystemExit(
            f"accounts.json: account {account['user']} does not classify {missing} "
            "— every bucket must be in `allow` or `deny`, or it goes untested"
        )

    checks = []
    for bucket in buckets:
        entry = allowed.get(bucket)
        if entry is None:
            checks.append(f"{bucket}:list:deny:-")
            checks.append(f"{bucket}:read:deny:{ABSENT_KEY}")
            checks.append(f"{bucket}:write:deny:{ABSENT_KEY}")
            continue
        access = entry["access"]
        probe = entry.get("write_probe_key", ".evidara-scoping-probe")
        checks.append(f"{bucket}:list:allow:-")
        if access == "wo":
            # Write-only: storing and purging is granted, reading back is not.
            checks.append(f"{bucket}:read:deny:{ABSENT_KEY}")
        if access in ("wo", "rw"):
            checks.append(f"{bucket}:write:allow:{probe}")
        else:
            checks.append(f"{bucket}:write:deny:{probe}")

    print(
        "\t".join(
            (
                account["user"],
                account["k8s_secret"],
                account["access_key_field"],
                account["secret_key_field"],
                " ".join(checks),
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
      if mc --config-dir "\$CFG" cat "u/\$bucket/\$key" >/dev/null 2>&1; then got=allow; else got=deny; fi
      ;;
    write)
      if echo evidara-scoping-probe | mc --config-dir "\$CFG" pipe "u/\$bucket/\$key" >/dev/null 2>&1; then
        got=allow
        mc --config-dir "\$CFG" rm "u/\$bucket/\$key" >/dev/null 2>&1 || true
      else
        got=deny
      fi
      ;;
    *) echo "    FAIL unknown check \$check"; fail=1; continue ;;
  esac
  if [ "\$got" = "\$expect" ]; then
    echo "    PASS \$bucket \$check -> \$expect"
  else
    echo "    FAIL \$bucket \$check -> expected \$expect, got \$got"
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
echo "OK: ${CHECKED} account(s) reach exactly the buckets they are scoped to"
