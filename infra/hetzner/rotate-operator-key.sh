#!/usr/bin/env bash
# Rotate PLATFORM_CONTROL_OPERATOR_API_KEY in the `evidara-auth` Secret.
#
# deploy-stage5.sh creates that Secret once and never touches an existing value,
# which is right for a deploy script and leaves no way to replace a key that
# leaked. This is that way.
#
# The key is an operator credential: `X-API-Key` against platform-control, and
# what projection-bridge presents when it writes projections. It is not in git
# and no Argo Application manages it, so the live Secret is the only copy.
#
# The new value never reaches stdout, argv or shell history. `kubectl patch -p`
# would put it in argv, where any local user reads it with `ps` — the exact
# exposure that prompted this script — so the patch goes through a 0600 file
# that is removed on exit, including on failure.

set -euo pipefail

NS="${NS:-evidara}"
SECRET="${SECRET:-evidara-auth}"
KEY="${KEY:-PLATFORM_CONTROL_OPERATOR_API_KEY}"

# Every workload that reads the Secret, whether by envFrom or a single
# secretKeyRef. Env vars are fixed at pod start, so a pod that is not restarted
# keeps presenting — or accepting — the old key. platform-control-api is the
# validator and projection-bridge is a sender; leaving either behind produces
# 401s that look like a broken deploy.
WORKLOADS=(
  deployment/platform-control-api
  deployment/platform-control-admin
  deployment/projection-bridge
  deployment/legal-search-api
  deployment/legal-search-frontend
)

usage() {
  cat <<'USAGE'
Usage: infra/hetzner/rotate-operator-key.sh [--dry-run] [--no-restart]

  --dry-run     Show what would happen; write nothing.
  --no-restart  Patch the Secret but leave pods alone. They keep the OLD key
                until restarted, so the rotation is not in effect.

Env: NS (evidara), SECRET (evidara-auth), KEY (PLATFORM_CONTROL_OPERATOR_API_KEY)
USAGE
}

DRY_RUN=0
RESTART=1
while [[ $# -gt 0 ]]; do
  case "$1" in
    --dry-run) DRY_RUN=1; shift ;;
    --no-restart) RESTART=0; shift ;;
    -h|--help) usage; exit 0 ;;
    *) echo "Unknown argument: $1" >&2; usage >&2; exit 2 ;;
  esac
done

for cmd in kubectl openssl base64; do
  command -v "$cmd" >/dev/null || { echo "error: $cmd not found" >&2; exit 1; }
done

kubectl -n "$NS" get secret "$SECRET" >/dev/null || {
  echo "error: secret $SECRET not found in namespace $NS." >&2
  echo "       Run infra/hetzner/deploy-stage5.sh to create it." >&2
  exit 1
}

kubectl -n "$NS" get secret "$SECRET" -o "jsonpath={.data.$KEY}" | grep -q . || {
  echo "error: $SECRET has no $KEY to rotate." >&2
  exit 1
}

if [[ "$DRY_RUN" == 1 ]]; then
  echo "==> DRY RUN — nothing will be written"
  echo "    would replace $KEY in secret $NS/$SECRET"
  [[ "$RESTART" == 1 ]] && printf '    would restart: %s\n' "${WORKLOADS[@]}"
  exit 0
fi

WORKDIR="$(mktemp -d)"
# Fires on success, error and interrupt alike: key material must not outlive
# the script even when it fails halfway.
cleanup() { rm -rf "$WORKDIR"; }
trap cleanup EXIT INT TERM
umask 077

echo "==> Reading the current key (kept only to prove the rotation took effect)"
kubectl -n "$NS" get secret "$SECRET" -o "jsonpath={.data.$KEY}" | base64 -d > "$WORKDIR/old"

echo "==> Generating a replacement"
openssl rand -hex 24 > "$WORKDIR/new"
if cmp -s "$WORKDIR/old" "$WORKDIR/new"; then
  echo "error: generated key equals the current one; refusing." >&2
  exit 1
fi

echo "==> Patching $NS/$SECRET"
printf '{"data":{"%s":"%s"}}' "$KEY" "$(base64 -w0 < "$WORKDIR/new")" > "$WORKDIR/patch.json"
kubectl -n "$NS" patch secret "$SECRET" --type merge --patch-file "$WORKDIR/patch.json" >/dev/null
echo "    patched"

if [[ "$RESTART" == 0 ]]; then
  echo "==> --no-restart: pods keep the OLD key. Rotation is NOT yet in effect."
  exit 0
fi

echo "==> Restarting the workloads that read it"
# All of them before waiting on any: the validator and its callers must not sit
# on opposite sides of the rotation for longer than necessary.
for w in "${WORKLOADS[@]}"; do
  kubectl -n "$NS" rollout restart "$w" >/dev/null && echo "    restarted $w"
done
for w in "${WORKLOADS[@]}"; do
  kubectl -n "$NS" rollout status "$w" --timeout=180s >/dev/null && echo "    ready $w"
done

echo "==> Verifying"
PC_URL="${PC_URL:-https://platform-control-api.ts.veyo.dev}"
probe() {  # $1 = key file -> prints the HTTP status
  curl -sS --max-time 20 -o /dev/null -w '%{http_code}' \
    "$PC_URL/v1/sources/blueprint-templates?limit=1" \
    -H "X-API-Key: $(cat "$1")" 2>/dev/null || echo "000"
}
new_code="$(probe "$WORKDIR/new")"
old_code="$(probe "$WORKDIR/old")"
echo "    new key -> HTTP $new_code (expect 200)"
echo "    old key -> HTTP $old_code (expect 401)"

if [[ "$new_code" != "200" || "$old_code" != "401" ]]; then
  echo "error: rotation did not verify. The Secret holds the new key, but the" >&2
  echo "       API does not behave as expected — check pod rollout and retry." >&2
  exit 1
fi

echo "==> Rotated. Anything holding the previous key must be updated:"
echo "    - local shells exporting EVIDARA_PLATFORM_CONTROL_API_KEY"
echo "    - read it back with:"
echo "      kubectl -n $NS get secret $SECRET -o jsonpath='{.data.$KEY}' | base64 -d"
