#!/usr/bin/env bash
# Prove the internal-beta corpus through platform-control local outbox replay.

set -euo pipefail

ROOT="$(cd "$(dirname "${BASH_SOURCE[0]}")/.." && pwd)"
TARGETS_FILE="${INTERNAL_BETA_REPLAY_TARGETS_FILE:-$ROOT/scripts/fixtures/internal-beta-normal-replay-targets.tsv}"
PC_URL="${EVIDARA_PLATFORM_CONTROL_URL:-}"
LS_URL="${EVIDARA_LEGAL_SEARCH_URL:-}"
JURISDICTION_ID="${EVIDARA_REPLAY_JURISDICTION_ID:-jur_ch_federal}"
AUTHORITY_ID="${EVIDARA_REPLAY_AUTHORITY_ID:-auth_fedlex}"
REQUEST_TIMEOUT_SECONDS="${EVIDARA_REPLAY_REQUEST_TIMEOUT_SECONDS:-30}"
RUN_POLL_ATTEMPTS="${EVIDARA_REPLAY_RUN_POLL_ATTEMPTS:-30}"
RUN_POLL_INTERVAL_SECONDS="${EVIDARA_REPLAY_RUN_POLL_INTERVAL_SECONDS:-5}"
REPLAY_COMMAND="${EVIDARA_REPLAY_COMMAND:-}"
WITHDRAW_COMMAND="${EVIDARA_REPLAY_WITHDRAW_COMMAND:-}"

if [[ -z "$PC_URL" || -z "$LS_URL" ]]; then
  echo "Set EVIDARA_PLATFORM_CONTROL_URL and EVIDARA_LEGAL_SEARCH_URL." >&2
  exit 2
fi

if [[ ! -f "$TARGETS_FILE" ]]; then
  echo "Replay targets file not found: $TARGETS_FILE" >&2
  exit 2
fi

for required_command in curl jq python3; do
  if ! command -v "$required_command" >/dev/null 2>&1; then
    echo "Missing required command: $required_command" >&2
    exit 2
  fi
done

PC_URL="${PC_URL%/}"
LS_URL="${LS_URL%/}"

pc_auth_args=()
ls_auth_args=()
if [[ -n "${EVIDARA_PLATFORM_CONTROL_TOKEN:-}" ]]; then
  pc_auth_args=(-H "Authorization: Bearer ${EVIDARA_PLATFORM_CONTROL_TOKEN}")
fi
if [[ -n "${EVIDARA_LEGAL_SEARCH_TOKEN:-}" ]]; then
  ls_auth_args=(-H "Authorization: Bearer ${EVIDARA_LEGAL_SEARCH_TOKEN}")
fi

curl_json() {
  local url="$1"
  shift
  curl -fsS --connect-timeout 5 --max-time 45 "$@" "$url"
}

post_pc() {
  local path="$1"
  local body="$2"
  curl_json "${PC_URL}${path}" \
    "${pc_auth_args[@]}" \
    -H "Accept: application/json" \
    -H "Content-Type: application/json" \
    -X POST \
    -d "$body"
}

get_pc() {
  local path="$1"
  curl_json "${PC_URL}${path}" "${pc_auth_args[@]}" -H "Accept: application/json"
}

get_ls() {
  local path="$1"
  shift
  curl -fsS --connect-timeout 5 --max-time 45 "${ls_auth_args[@]}" -H "Accept: application/json" "$@" "${LS_URL}${path}"
}

json_string() {
  python3 -c 'import json,sys; print(json.dumps(sys.argv[1]))' "$1"
}

declare -a run_ids=()
declare -a titles=()

echo "## Creating platform-control replay runs"
while IFS=$'\t' read -r key title source_url || [[ -n "${key:-}" ]]; do
  key="${key//$'\r'/}"
  title="${title//$'\r'/}"
  source_url="${source_url//$'\r'/}"
  [[ -z "${key// }" ]] && continue
  [[ "$key" =~ ^[[:space:]]*# ]] && continue

  source_name="Internal beta replay ${key} $(date -u +%Y%m%d%H%M%S)"
  source_body="$(python3 - <<PY
import json
print(json.dumps({
    "name": ${source_name@Q},
    "jurisdiction_id": ${JURISDICTION_ID@Q},
    "authority_id": ${AUTHORITY_ID@Q},
}))
PY
)"
  source_response="$(post_pc "/v1/sources" "$source_body")"
  source_id="$(echo "$source_response" | jq -r '.source_id')"

  version_body="$(python3 - <<PY
import json
print(json.dumps({
    "version_label": "normal-replay-${key}-$(date -u +%Y%m%d%H%M%S)",
    "acquisition_spec": {
        "provider": "deterministic_http",
        "seed_url": ${source_url@Q},
        "request_timeout_seconds": int(${REQUEST_TIMEOUT_SECONDS@Q}),
        "tenant_id": "tenant_public",
        "corpus_id": "corpus_public_ch_federal_law",
        "scope_type": "global_public",
        "source_origin_kind": "official_primary",
        "trust_tier": "authoritative",
        "language_codes": ["en"],
        "document_type_hint": "law",
    },
}))
PY
)"
  version_response="$(post_pc "/v1/sources/${source_id}/versions" "$version_body")"
  source_version_id="$(echo "$version_response" | jq -r '.source_version_id')"
  post_pc "/v1/versions/${source_version_id}/approve" "{}" >/dev/null
  run_response="$(post_pc "/v1/runs" "{\"source_id\":\"${source_id}\",\"source_version_id\":\"${source_version_id}\"}")"
  run_id="$(echo "$run_response" | jq -r '.run_id')"
  run_ids+=("$run_id")
  titles+=("$title")
  echo "- ${key}: run=${run_id} title=$(json_string "$title")"
done < "$TARGETS_FILE"

echo ""
echo "## Waiting for acquisition runs"
for run_id in "${run_ids[@]}"; do
  for attempt in $(seq 1 "$RUN_POLL_ATTEMPTS"); do
    run_payload="$(get_pc "/v1/runs/${run_id}")"
    status="$(echo "$run_payload" | jq -r '.status')"
    echo "- ${run_id}: ${status} (${attempt}/${RUN_POLL_ATTEMPTS})"
    if [[ "$status" == "completed" ]]; then
      break
    fi
    if [[ "$status" == "failed" || "$status" == "cancelled" ]]; then
      echo "$run_payload" | jq .
      exit 1
    fi
    if [[ "$attempt" == "$RUN_POLL_ATTEMPTS" ]]; then
      echo "Timed out waiting for run ${run_id}." >&2
      exit 1
    fi
    sleep "$RUN_POLL_INTERVAL_SECONDS"
  done
done

echo ""
echo "## Replaying local outbox"
if [[ -z "$REPLAY_COMMAND" ]]; then
  REPLAY_COMMAND="document_intelligence_replay_local_outbox --legal-search-api-url ${LS_URL} --keep-projections"
fi
eval "$REPLAY_COMMAND"

echo ""
echo "## Checking replay projection history"
for i in "${!run_ids[@]}"; do
  run_id="${run_ids[$i]}"
  title="${titles[$i]}"
  history="$(get_ls "/v1/projections/events/history" \
    --get \
    --data-urlencode "run_id=${run_id}" \
    --data-urlencode "limit=20" \
    --data-urlencode "offset=0")"
  applied="$(echo "$history" | jq -r '[.data[] | select(.status=="applied")] | length')"
  if [[ "$applied" -lt 1 ]]; then
    echo "No applied projection for replay run ${run_id} (${title})." >&2
    echo "$history" | jq .
    exit 1
  fi
  echo "- ${run_id}: applied=${applied} title=$(json_string "$title")"
done

echo ""
echo "## Withdrawing replay projections"
if [[ -z "$WITHDRAW_COMMAND" ]]; then
  WITHDRAW_COMMAND="document_intelligence_replay_local_outbox --legal-search-api-url ${LS_URL} --withdraw-only"
fi
eval "$WITHDRAW_COMMAND"

echo ""
echo "## Verifying canonical beta corpus remains exact"
EVIDARA_LEGAL_SEARCH_URL="$LS_URL" EVIDARA_LEGAL_SEARCH_TOKEN="${EVIDARA_LEGAL_SEARCH_TOKEN:-}" \
  "$ROOT/scripts/check-internal-beta-query-pack.sh"

echo ""
echo "Internal beta normal replay proof passed."
