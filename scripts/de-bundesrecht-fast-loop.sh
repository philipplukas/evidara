#!/usr/bin/env bash
set -euo pipefail

SCRIPT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
# shellcheck source=scripts/fast-loop-evidence.sh
source "${SCRIPT_DIR}/fast-loop-evidence.sh"

ENVIRONMENT="dev"
TEMPLATE_ID="deterministic_http_bundesrecht_codes"
JURISDICTION_ID="jur_de"
AUTHORITY_ID="auth_de_bundesrecht"
MAX_RESOURCES=20
KEEP_SOURCE=0
JSON_OUTPUT=0
DRY_RUN=0
MAX_POLLS=60
POLL_INTERVAL=5
WORKDIR_ROOT="${TMPDIR:-/tmp}/de-bundesrecht-fast-loop"
RUN_DIR=""
SOURCE_ID=""
SOURCE_VERSION_ID=""
RUN_ID=""
STARTED_AT_UTC="$(date -u +%Y-%m-%dT%H:%M:%SZ)"

usage() {
  cat <<'EOF'
Usage: scripts/de-bundesrecht-fast-loop.sh [options]

Run a narrow DE Bundesrecht preview against platform-control on Cloud Run and verify:
  - EUR-Lex HTML capture via Cellar SPARQL
  - DI accepted / processing / canonical_ready
  - document.processed lifecycle
  - minimum EU legal-text quality gates

Options:
  --env <dev|staging|prod>       Target environment (default: dev)
  --project <id>                 GCP project override
  --region <region>              Cloud Run region override
  --impersonate-sa <email>       Service account override
  --pc-url <url>                 Platform-control URL override
  --template <template-id>       Source blueprint template (default: eur_lex_sparql_regulation_en)
  --max-resources <n>            Preview scope max_resources (default: 5)
  --max-polls <n>                Maximum run polls (default: 60)
  --poll-interval <seconds>      Run poll interval (default: 5)
  --out-dir <path>               Exact directory for persisted evidence bundle
  --json                         Emit final machine-readable summary JSON
  --dry-run                      Print resolved settings and exit before mutating APIs
  --keep-source                  Do not report cleanup guidance as follow-up work
  --workdir-root <path>          Directory for persisted evidence bundles
  -h, --help                     Show this help
EOF
}

while [[ $# -gt 0 ]]; do
  case "$1" in
    --env)
      ENVIRONMENT="${2:?missing value for --env}"
      shift 2
      ;;
    --template)
      TEMPLATE_ID="${2:?missing value for --template}"
      shift 2
      ;;
    --project)
      GCP_PROJECT_ID="${2:?missing value for --project}"
      shift 2
      ;;
    --region)
      GCP_REGION="${2:?missing value for --region}"
      shift 2
      ;;
    --impersonate-sa)
      EVIDARA_GCP_IMPERSONATE_SERVICE_ACCOUNT="${2:?missing value for --impersonate-sa}"
      shift 2
      ;;
    --pc-url)
      EVIDARA_PLATFORM_CONTROL_URL="${2:?missing value for --pc-url}"
      shift 2
      ;;
    --max-resources)
      MAX_RESOURCES="${2:?missing value for --max-resources}"
      shift 2
      ;;
    --max-polls)
      MAX_POLLS="${2:?missing value for --max-polls}"
      shift 2
      ;;
    --poll-interval)
      POLL_INTERVAL="${2:?missing value for --poll-interval}"
      shift 2
      ;;
    --json)
      JSON_OUTPUT=1
      shift
      ;;
    --dry-run)
      DRY_RUN=1
      shift
      ;;
    --keep-source)
      KEEP_SOURCE=1
      shift
      ;;
    --out-dir)
      RUN_DIR="${2:?missing value for --out-dir}"
      shift 2
      ;;
    --workdir-root)
      WORKDIR_ROOT="${2:?missing value for --workdir-root}"
      shift 2
      ;;
    -h|--help)
      usage
      exit 0
      ;;
    *)
      echo "Unknown argument: $1" >&2
      usage >&2
      exit 1
      ;;
  esac
done

require_cmd() {
  command -v "$1" >/dev/null 2>&1 || {
    echo "error: missing command '$1'" >&2
    exit 1
  }
}

require_cmd gcloud
require_cmd curl
require_cmd jq

PROJECT_ID="${GCP_PROJECT_ID:-project-dacd6b7b-dc96-4534-b82}"
REGION="${GCP_REGION:-europe-west6}"
SA="${EVIDARA_GCP_IMPERSONATE_SERVICE_ACCOUNT:-}"

if [[ -z "${SA}" ]]; then
  echo "error: set EVIDARA_GCP_IMPERSONATE_SERVICE_ACCOUNT before running this loop." >&2
  exit 1
fi

mkdir -p "${WORKDIR_ROOT}"
if [[ -z "${RUN_DIR}" ]]; then
  RUN_DIR="${WORKDIR_ROOT}/$(date -u +%Y%m%dT%H%M%SZ)"
fi
mkdir -p "${RUN_DIR}"

PC_URL="${EVIDARA_PLATFORM_CONTROL_URL:-$(gcloud run services describe "platform-control-api-${ENVIRONMENT}" --project "${PROJECT_ID}" --region "${REGION}" --format='value(status.url)')}"

export EVIDARA_GCP_IMPERSONATE_SERVICE_ACCOUNT="${SA}"
export EVIDARA_PLATFORM_CONTROL_URL="${PC_URL%/}"

eval "$(
  ./scripts/mint-cloud-run-tokens.sh
)"

curl_json() {
  curl -fsS \
    -H "Authorization: Bearer ${EVIDARA_PLATFORM_CONTROL_TOKEN}" \
    "$@"
}

log() {
  printf '%s\n' "$*" >&2
}

save_json() {
  local path="$1"
  cat >"${RUN_DIR}/${path}"
}

expected_title_regex() {
  printf '%s' '(Gesetz|Verordnung|Ordnung|Grundgesetz|Gesetzbuch|Buch)'
}

poll_terminal_run_status() {
  local max_polls="${1:-60}"
  local interval="${2:-5}"
  local status=""
  for i in $(seq 1 "${max_polls}"); do
    curl_json "${PC_URL}/v1/runs/${RUN_ID}" | tee "${RUN_DIR}/run-state.json" >/dev/null
    status="$(jq -r '.status // empty' < "${RUN_DIR}/run-state.json")"
    log "poll ${i}/${max_polls}: run status=${status}"
    if [[ "${status}" == "completed" || "${status}" == "failed" || "${status}" == "cancelled" ]]; then
      printf '%s' "${status}"
      return 0
    fi
    sleep "${interval}"
  done
  printf '%s' "${status}"
  return 0
}

log "==> DE Bundesrecht fast loop"
log "    environment=${ENVIRONMENT}"
log "    project=${PROJECT_ID}"
log "    region=${REGION}"
log "    template=${TEMPLATE_ID}"
log "    jurisdiction_id=${JURISDICTION_ID}"
log "    authority_id=${AUTHORITY_ID}"
log "    max_resources=${MAX_RESOURCES}"
log "    max_polls=${MAX_POLLS}"
log "    poll_interval=${POLL_INTERVAL}"
log "    run_dir=${RUN_DIR}"

if [[ "${DRY_RUN}" -eq 1 ]]; then
  log "==> Dry run: stopping before API writes"
  exit 0
fi

curl_json "${PC_URL}/health" | save_json "platform-control-health.json"

VERSION_LABEL="de-bundesrecht-fast-loop-$(date -u +%Y%m%dT%H%M%SZ)"
CREATE_PAYLOAD="$(jq -n \
  --arg version_label "${VERSION_LABEL}" \
  --arg template_id "${TEMPLATE_ID}" \
  --arg jurisdiction_id "${JURISDICTION_ID}" \
  --arg authority_id "${AUTHORITY_ID}" \
  '{
    source: {
      name: "DE Bundesrecht fast-loop source",
      jurisdiction_id: $jurisdiction_id,
      authority_id: $authority_id,
      source_type: "api",
      document_family: "law"
    },
    source_version: {
      version_label: $version_label,
      overlay_id: "de",
      provider_template_id: $template_id
    }
  }')"

log "==> Creating source + version"
curl -fsS -X POST "${PC_URL}/v1/sources/with-version" \
  -H "Authorization: Bearer ${EVIDARA_PLATFORM_CONTROL_TOKEN}" \
  -H "Content-Type: application/json" \
  -d "${CREATE_PAYLOAD}" | tee "${RUN_DIR}/create.json" >/dev/null

SOURCE_ID="$(jq -r '.source.source_id // .source.id // .source_id // empty' < "${RUN_DIR}/create.json")"
SOURCE_VERSION_ID="$(jq -r '.source_version.source_version_id // .source_version.id // .source_version_id // empty' < "${RUN_DIR}/create.json")"

if [[ -z "${SOURCE_ID}" || -z "${SOURCE_VERSION_ID}" ]]; then
  echo "error: source creation did not return source/source_version ids" >&2
  cat "${RUN_DIR}/create.json" >&2
  exit 1
fi

log "==> Checking readiness"
curl_json "${PC_URL}/v1/runs/readiness?source_id=${SOURCE_ID}&source_version_id=${SOURCE_VERSION_ID}&mode=preview" | tee "${RUN_DIR}/readiness.json" >/dev/null
READY="$(jq -r '.ready' < "${RUN_DIR}/readiness.json")"
if [[ "${READY}" != "true" ]]; then
  echo "error: readiness returned ready=${READY}" >&2
  cat "${RUN_DIR}/readiness.json" >&2
  exit 1
fi

log "==> Approving source version"
curl -fsS -X POST "${PC_URL}/v1/versions/${SOURCE_VERSION_ID}/approve" \
  -H "Authorization: Bearer ${EVIDARA_PLATFORM_CONTROL_TOKEN}" | tee "${RUN_DIR}/approve.json" >/dev/null

RUN_PAYLOAD="$(jq -n --arg source_id "${SOURCE_ID}" --arg source_version_id "${SOURCE_VERSION_ID}" --argjson max_resources "${MAX_RESOURCES}" '{
  source_id: $source_id,
  source_version_id: $source_version_id,
  mode: "preview",
  scope: {
    kind: "discovered_subset",
    max_resources: $max_resources
  }
}')"

log "==> Launching preview run"
RUN_HTTP_CODE="$(
  curl -sS -o "${RUN_DIR}/run-create.json" -w '%{http_code}' \
    -X POST "${PC_URL}/v1/runs" \
    -H "Authorization: Bearer ${EVIDARA_PLATFORM_CONTROL_TOKEN}" \
    -H "Content-Type: application/json" \
    -d "${RUN_PAYLOAD}" || true
)"
if [[ "${RUN_HTTP_CODE}" != "200" && "${RUN_HTTP_CODE}" != "201" ]]; then
  echo "error: run creation failed with HTTP ${RUN_HTTP_CODE:-000}" >&2
  if [[ -s "${RUN_DIR}/run-create.json" ]]; then
    cat "${RUN_DIR}/run-create.json" >&2
  fi
  exit 1
fi

RUN_ID="$(jq -r '.run_id // .id // empty' < "${RUN_DIR}/run-create.json")"
if [[ -z "${RUN_ID}" ]]; then
  echo "error: run creation did not return run_id" >&2
  cat "${RUN_DIR}/run-create.json" >&2
  exit 1
fi

FINAL_STATUS="$(poll_terminal_run_status "${MAX_POLLS}" "${POLL_INTERVAL}")"
if [[ "${FINAL_STATUS}" != "completed" ]]; then
  echo "error: run finished with status=${FINAL_STATUS}" >&2
  cat "${RUN_DIR}/run-state.json" >&2
  exit 1
fi

log "==> Collecting run diagnostics"
curl_json "${PC_URL}/v1/runs/${RUN_ID}/provider-jobs" | tee "${RUN_DIR}/provider-jobs.json" >/dev/null
curl_json "${PC_URL}/v1/runs/${RUN_ID}/preview-summary" | tee "${RUN_DIR}/preview-summary.json" >/dev/null
curl_json "${PC_URL}/v1/runs/${RUN_ID}/captured-resources" | tee "${RUN_DIR}/captured-resources.json" >/dev/null
curl_json "${PC_URL}/v1/runs/${RUN_ID}/raw-artifacts" | tee "${RUN_DIR}/raw-artifacts.json" >/dev/null

log "==> Waiting for DI processing and lifecycle signals"
for i in $(seq 1 24); do
  curl_json "${PC_URL}/v1/runs/${RUN_ID}/processing-status" | tee "${RUN_DIR}/processing-status.json" >/dev/null
  curl_json "${PC_URL}/v1/runs/${RUN_ID}/document-lifecycle" | tee "${RUN_DIR}/document-lifecycle.json" >/dev/null
  canonical_ready_count="$(jq -r '[.data[]? | select(.status=="canonical_ready")] | length' < "${RUN_DIR}/processing-status.json")"
  processed_count="$(jq -r '[.data[]? | select(.event_type=="document.processed")] | length' < "${RUN_DIR}/document-lifecycle.json")"
  if [[ "${canonical_ready_count}" -gt 0 && "${processed_count}" -gt 0 ]]; then
    break
  fi
  sleep 5
done

TITLE_REGEX="$(expected_title_regex)"
# EUR-Lex Cellar may return text/html or application/xhtml+xml
content_type_html_count="$(jq -r '[.content_type_breakdown[]? | select(.content_type=="text/html" or .content_type=="application/xhtml+xml") | .count] | add // 0' < "${RUN_DIR}/preview-summary.json")"
captured_count="$(jq -r '.captured_resources_count // (.data | length) // 0' < "${RUN_DIR}/preview-summary.json")"
raw_artifact_count="$(jq -r '.total // (.data | length) // 0' < "${RUN_DIR}/raw-artifacts.json")"
title_ok="$(jq -r --arg title_regex "${TITLE_REGEX}" '[.data[]? | select((.title // "") | test($title_regex; "i"))] | length' < "${RUN_DIR}/captured-resources.json")"
# gesetze-im-internet.de URLs
source_url_ok="$(jq -r '[.data[]? | select((.final_url // "") | test("gesetze-im-internet\\.de"))] | length' < "${RUN_DIR}/captured-resources.json")"
accepted_count="$(jq -r '[.data[]? | select(.status=="accepted")] | length' < "${RUN_DIR}/processing-status.json")"
processing_count="$(jq -r '[.data[]? | select(.status=="processing")] | length' < "${RUN_DIR}/processing-status.json")"
canonical_ready_count="$(jq -r '[.data[]? | select(.status=="canonical_ready")] | length' < "${RUN_DIR}/processing-status.json")"
processed_count="$(jq -r '[.data[]? | select(.event_type=="document.processed")] | length' < "${RUN_DIR}/document-lifecycle.json")"

verdict="pass"
if [[ "${captured_count}" -lt 1 || "${raw_artifact_count}" -lt 1 ]]; then
  verdict="provider_failed"
elif [[ "${canonical_ready_count}" -lt 1 || "${processed_count}" -lt 1 ]]; then
  verdict="downstream_failed"
elif [[ "${title_ok}" -lt 1 || "${source_url_ok}" -lt 1 ]]; then
  verdict="pipeline_pass_content_suspect"
fi

SUMMARY_JSON="$(jq -n \
  --arg environment "${ENVIRONMENT}" \
  --arg run_mode "preview" \
  --arg template_id "${TEMPLATE_ID}" \
  --arg source_id "${SOURCE_ID}" \
  --arg source_version_id "${SOURCE_VERSION_ID}" \
  --arg run_id "${RUN_ID}" \
  --arg verdict "${verdict}" \
  --arg run_dir "${RUN_DIR}" \
  --arg started_at_utc "${STARTED_AT_UTC}" \
  --arg completed_at_utc "$(date -u +%Y-%m-%dT%H:%M:%SZ)" \
  --argjson max_resources "${MAX_RESOURCES}" \
  --argjson captured_count "${captured_count}" \
  --argjson raw_artifact_count "${raw_artifact_count}" \
  --argjson content_type_html_count "${content_type_html_count}" \
  --argjson accepted_count "${accepted_count}" \
  --argjson processing_count "${processing_count}" \
  --argjson canonical_ready_count "${canonical_ready_count}" \
  --argjson processed_count "${processed_count}" \
  --argjson title_ok "${title_ok}" \
  --argjson source_url_ok "${source_url_ok}" \
  '{
    run_mode: $run_mode,
    environment: $environment,
    template_id: $template_id,
    source_id: $source_id,
    source_version_id: $source_version_id,
    run_id: $run_id,
    max_resources: $max_resources,
    verdict: $verdict,
    run_dir: $run_dir,
    started_at_utc: $started_at_utc,
    completed_at_utc: $completed_at_utc,
    checks: {
      captured_count: $captured_count,
      raw_artifact_count: $raw_artifact_count,
      content_type_html_count: $content_type_html_count,
      accepted_count: $accepted_count,
      processing_count: $processing_count,
      canonical_ready_count: $canonical_ready_count,
      processed_count: $processed_count,
      title_ok: $title_ok,
      source_url_ok: $source_url_ok
    }
  }')"

printf '%s\n' "${SUMMARY_JSON}" > "${RUN_DIR}/summary.json"
render_fast_loop_evidence_markdown "${RUN_DIR}/summary.json" "${RUN_DIR}/evidence-summary.md" "DE Bundesrecht"

if [[ "${JSON_OUTPUT}" -eq 1 ]]; then
  cat "${RUN_DIR}/summary.json"
else
  log "==> Summary"
  jq . < "${RUN_DIR}/summary.json" >&2
  log "==> Evidence markdown"
  cat "${RUN_DIR}/evidence-summary.md" >&2
  if [[ "${KEEP_SOURCE}" -eq 0 ]]; then
    log "==> Note: created source_id=${SOURCE_ID} source_version_id=${SOURCE_VERSION_ID}"
  fi
fi

if [[ "${verdict}" != "pass" ]]; then
  exit 1
fi
