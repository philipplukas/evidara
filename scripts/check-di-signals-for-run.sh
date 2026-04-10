#!/usr/bin/env bash
set -euo pipefail

# Query platform-control for the same DI signal endpoints as e2e-smoke-test.sh step 7.
# Use after a failed smoke (copy run_id from the log) or any completed run — no full E2E required.
#
# Usage:
#   ./scripts/check-di-signals-for-run.sh [--env dev|staging|prod] [--watch] RUN_ID
#
# Environment (align with e2e-smoke-test.sh and docs/setup/gcp-local-cloud-run-auth.md):
#   GCP_PROJECT_ID / GCP_REGION
#   EVIDARA_GCP_IMPERSONATE_SERVICE_ACCOUNT — mint audience-scoped ID tokens (private Cloud Run)
#   E2E_PC_ID_TOKEN — optional; if set, used for requests to platform-control (skip mint)
#   EVIDARA_PLATFORM_CONTROL_API_KEY or PLATFORM_CONTROL_API_KEY — X-API-Key when PC has keys configured
#
# Watch mode (mimics step 7 timing):
#   E2E_DI_MAX_POLLS (default 24), E2E_DI_POLL_INTERVAL (default 5)

ENVIRONMENT="dev"
WATCH=0
RUN_ID=""

while [[ $# -gt 0 ]]; do
  case "$1" in
    --env)
      ENVIRONMENT="${2:?missing value for --env}"
      shift 2
      ;;
    --watch)
      WATCH=1
      shift
      ;;
    -h | --help)
      sed -n '1,25p' "$0" | tail -n +2
      exit 0
      ;;
    *)
      if [[ -n "${RUN_ID}" ]]; then
        echo "Unexpected extra argument: $1" >&2
        exit 1
      fi
      RUN_ID="$1"
      shift
      ;;
  esac
done

if [[ -z "${RUN_ID}" ]]; then
  echo "Usage: $0 [--env dev|staging|prod] [--watch] RUN_ID" >&2
  exit 1
fi

PROJECT_ID="${GCP_PROJECT_ID:-data-platform-dev-492214}"
REGION="${GCP_REGION:-europe-west6}"

_gcloud_print_identity_token() {
  local -a args=(auth print-identity-token)
  if [[ -n "${EVIDARA_GCP_IMPERSONATE_SERVICE_ACCOUNT:-}" ]]; then
    args+=(--impersonate-service-account="${EVIDARA_GCP_IMPERSONATE_SERVICE_ACCOUNT}")
  fi
  if [[ -n "${1:-}" ]]; then
    args+=(--audiences="$1")
  fi
  gcloud "${args[@]}" 2>/dev/null || true
}

PC_URL=$(gcloud run services describe "platform-control-api-${ENVIRONMENT}" \
  --project "${PROJECT_ID}" --region "${REGION}" \
  --format='value(status.url)' 2>/dev/null) || {
  echo "❌ Could not resolve platform-control-api URL (gcloud run services describe …)" >&2
  exit 1
}

API_KEY_HEADER=()
_PC_KEY="${EVIDARA_PLATFORM_CONTROL_API_KEY:-${PLATFORM_CONTROL_API_KEY:-}}"
if [[ -n "${_PC_KEY}" ]]; then
  API_KEY_HEADER=(-H "X-API-Key: ${_PC_KEY}")
fi

curl_json() {
  local auth_args=()
  if [[ -n "${E2E_PC_ID_TOKEN:-}" ]]; then
    auth_args=(-H "Authorization: Bearer ${E2E_PC_ID_TOKEN}")
  elif command -v gcloud >/dev/null 2>&1; then
    local audience_token
    audience_token="$(_gcloud_print_identity_token "${PC_URL}")"
    if [[ -n "${audience_token}" ]]; then
      auth_args=(-H "Authorization: Bearer ${audience_token}")
    fi
  fi
  curl -fsS --connect-timeout 5 --max-time 30 "${auth_args[@]}" "${API_KEY_HEADER[@]}" "$@"
}

if [[ -n "${EVIDARA_GCP_IMPERSONATE_SERVICE_ACCOUNT:-}" ]] && [[ -z "${E2E_PC_ID_TOKEN:-}" ]]; then
  if [[ -z "$(_gcloud_print_identity_token "${PC_URL}")" ]]; then
    echo "❌ Failed to mint Cloud Run identity token for ${PC_URL}" >&2
    echo "   Set EVIDARA_GCP_IMPERSONATE_SERVICE_ACCOUNT and ensure token creator + run.invoker." >&2
    exit 1
  fi
fi

print_snapshot() {
  local run_json status_json lifecycle_json
  run_json=$(curl_json "${PC_URL}/v1/runs/${RUN_ID}")
  status_json=$(curl_json "${PC_URL}/v1/runs/${RUN_ID}/processing-status")
  lifecycle_json=$(curl_json "${PC_URL}/v1/runs/${RUN_ID}/document-lifecycle")

  local status_count canonical_ready processed
  status_count=$(echo "${status_json}" | jq -r '.data | length')
  canonical_ready=$(echo "${status_json}" | jq -r '[.data[] | select(.status=="canonical_ready")] | length')
  processed=$(echo "${lifecycle_json}" | jq -r '[.data[] | select(.event_type=="document.processed")] | length')

  echo "📡 ${PC_URL}"
  echo "🔎 run_id=${RUN_ID}"
  echo "   GET /v1/runs/... → $(echo "${run_json}" | jq -c '{status, artifacts_count, captured_resources_count, failure_reason}')"
  echo "   processing-status rows=${status_count}, canonical_ready=${canonical_ready}"
  echo "   document.processed count=${processed}"
  echo ""
  echo "--- processing-status (raw) ---"
  echo "${status_json}" | jq .
  echo "--- document-lifecycle (raw) ---"
  echo "${lifecycle_json}" | jq .

  if [[ "${canonical_ready}" -gt 0 && "${processed}" -gt 0 ]]; then
    return 0
  fi
  return 1
}

if [[ "${WATCH}" -eq 0 ]]; then
  print_snapshot || true
  exit 0
fi

MAX="${E2E_DI_MAX_POLLS:-24}"
INTERVAL="${E2E_DI_POLL_INTERVAL:-5}"
for i in $(seq 1 "${MAX}"); do
  echo "── poll ${i}/${MAX} ──"
  if print_snapshot; then
    echo "✅ DI signals present (canonical_ready + document.processed)"
    exit 0
  fi
  if [[ "${i}" -eq "${MAX}" ]]; then
    echo "❌ Timed out (same condition as e2e step 7)" >&2
    exit 1
  fi
  sleep "${INTERVAL}"
done
