#!/usr/bin/env bash
set -euo pipefail

# CH federal court decisions (BGer/BVGer) fast-loop canary.
#
# Mirrors scripts/ch-fedlex-fast-loop.sh but drives the `ch_court_decisions`
# provider and asserts case-law content gates (docket, court host, decision
# markers) instead of legislation gates.
#
# READINESS NOTE: the `ch_court_decisions` provider ships
# readiness=awaiting_evidence — NOT a scaffold. Its fetch/parse logic is
# implemented and unit-tested; what is missing is acceptance evidence, which is
# what this harness produces. Run it with `--mode acceptance`: the two-key lock
# refuses `preview` for a provider awaiting evidence, and admits an acceptance
# run precisely so the evidence can be captured without an engineer (#743).
# Its blueprint templates (ch_court_decisions_bger / _bvger) ship
# `enabled: false`. Until an operator flips both keys with acceptance evidence
# (#530), a live run stops at readiness/two-key-lock. This script is the
# acceptance harness to run *at* live-enablement: point --pc-url at an env whose
# template has been enabled, capture a `pass` verdict, and use it as the
# evidence that justifies the flip.

SCRIPT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
# shellcheck source=scripts/fast-loop-evidence.sh
source "${SCRIPT_DIR}/fast-loop-evidence.sh"

ENVIRONMENT="dev"
TEMPLATE_ID="ch_court_decisions_bger"
MAX_RESOURCES=25
KEEP_SOURCE=0
JSON_OUTPUT=0
DRY_RUN=0
COPY_EVIDENCE=0
MAX_POLLS=60
# `ch_court_decisions` is readiness=awaiting_evidence, so `preview` is refused by
# the lock. Default stays `preview` for consistency with the sibling harnesses;
# capture evidence with `--mode acceptance` (#743, #530).
RUN_MODE="preview"
POLL_INTERVAL=5
WORKDIR_ROOT="${TMPDIR:-/tmp}/ch-bger-fast-loop"
RUN_DIR=""
SOURCE_ID=""
SOURCE_VERSION_ID=""
RUN_ID=""
# Self-hosted (Hetzner) auth: when an operator X-API-Key is supplied (flag or env),
# the loop skips gcloud/Cloud-Run identity-token minting and authenticates with
# `X-API-Key` against an explicit `--pc-url`. See scripts/ch-fedlex-fast-loop.sh.
PC_API_KEY="${EVIDARA_PLATFORM_CONTROL_API_KEY:-}"
STARTED_AT_UTC="$(date -u +%Y-%m-%dT%H:%M:%SZ)"

usage() {
  cat <<'EOF'
Usage: scripts/ch-bger-fast-loop.sh [options]

Run a narrow CH federal court-decisions preview against platform-control and verify:
  - text/html capture from a Swiss federal court host
  - DI accepted / processing / canonical_ready
  - document.processed lifecycle
  - minimum case-law content quality gates (docket, decision markers)

Options:
  --env <dev|staging|prod>       Target environment (default: dev)
  --project <id>                 GCP project override
  --region <region>              Cloud Run region override
  --impersonate-sa <email>       Service account override
  --pc-url <url>                 Platform-control URL override
  --ls-url <url>                 Legal-search URL override
  --api-key <key>                Operator X-API-Key (self-hosted / Hetzner mode).
                                 When set, skips gcloud + Cloud-Run token minting and
                                 authenticates with X-API-Key against --pc-url.
                                 Also read from EVIDARA_PLATFORM_CONTROL_API_KEY.
  --template <template-id>       Source blueprint template (default: ch_court_decisions_bger)
  --max-resources <n>            Preview scope max_resources (default: 25)
  --mode <preview|acceptance|production>
                                 Run mode (default: preview). `ch_court_decisions` is
                                 readiness=awaiting_evidence, so capturing its first
                                 evidence needs --mode acceptance (#743).
  --max-polls <n>                Maximum run polls (default: 60)
  --poll-interval <seconds>      Run poll interval (default: 5)
  --out-dir <path>               Exact directory for persisted evidence bundle
  --json                         Emit final machine-readable summary JSON
  --dry-run                      Print resolved settings and exit before mutating APIs
  --keep-source                  Suppress the acceptance-source note. The source is stable and
                                 reused across runs (#766); there is nothing to clean up.
  --copy-evidence                Copy evidence markdown to docs/runbooks/evidence/
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
    --api-key)
      PC_API_KEY="${2:?missing value for --api-key}"
      shift 2
      ;;
    --ls-url)
      EVIDARA_LEGAL_SEARCH_URL="${2:?missing value for --ls-url}"
      shift 2
      ;;
    --max-resources)
      MAX_RESOURCES="${2:?missing value for --max-resources}"
      shift 2
      ;;
    --mode)
      RUN_MODE="${2:?missing value for --mode}"
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
    --copy-evidence)
      COPY_EVIDENCE=1
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

require_cmd curl
require_cmd jq
case "${RUN_MODE}" in
  preview|acceptance|production) ;;
  *)
    echo "error: --mode must be preview, acceptance or production (got '${RUN_MODE}')" >&2
    exit 1
    ;;
esac


mkdir -p "${WORKDIR_ROOT}"
if [[ -z "${RUN_DIR}" ]]; then
  RUN_DIR="${WORKDIR_ROOT}/$(date -u +%Y%m%dT%H%M%SZ)"
fi
mkdir -p "${RUN_DIR}"

# Authority + attribution derived from the template so the create payload targets
# the right federal court.
case "${TEMPLATE_ID}" in
  *bvger*)
    AUTHORITY_ID="auth_bvger"
    ;;
  *)
    AUTHORITY_ID="auth_bger"
    ;;
esac

# Auth header args reused by every platform-control call.
PC_AUTH_HEADER=()

if [[ -n "${PC_API_KEY}" ]]; then
  # Self-hosted (Hetzner) mode: X-API-Key against an explicit platform-control URL.
  if [[ -z "${EVIDARA_PLATFORM_CONTROL_URL:-}" ]]; then
    echo "error: self-hosted mode (--api-key) requires --pc-url / EVIDARA_PLATFORM_CONTROL_URL." >&2
    exit 1
  fi
  PROJECT_ID="self-hosted"
  REGION="self-hosted"
  PC_URL="${EVIDARA_PLATFORM_CONTROL_URL%/}"
  LS_URL="${EVIDARA_LEGAL_SEARCH_URL:-}"
  export EVIDARA_PLATFORM_CONTROL_URL="${PC_URL}"
  [[ -n "${LS_URL}" ]] && export EVIDARA_LEGAL_SEARCH_URL="${LS_URL%/}"
  PC_AUTH_HEADER=(-H "X-API-Key: ${PC_API_KEY}")
else
  # Managed (GCP Cloud Run) mode: impersonated identity token as a Bearer credential.
  require_cmd gcloud

  PROJECT_ID="${GCP_PROJECT_ID:-project-dacd6b7b-dc96-4534-b82}"
  REGION="${GCP_REGION:-europe-west6}"
  SA="${EVIDARA_GCP_IMPERSONATE_SERVICE_ACCOUNT:-}"

  if [[ -z "${SA}" ]]; then
    echo "error: set EVIDARA_GCP_IMPERSONATE_SERVICE_ACCOUNT (or pass --api-key for self-hosted)." >&2
    exit 1
  fi

  PC_URL="${EVIDARA_PLATFORM_CONTROL_URL:-$(gcloud run services describe "platform-control-api-${ENVIRONMENT}" --project "${PROJECT_ID}" --region "${REGION}" --format='value(status.url)')}"
  LS_URL="${EVIDARA_LEGAL_SEARCH_URL:-$(gcloud run services describe "legal-search-api-${ENVIRONMENT}" --project "${PROJECT_ID}" --region "${REGION}" --format='value(status.url)')}"

  export EVIDARA_GCP_IMPERSONATE_SERVICE_ACCOUNT="${SA}"
  export EVIDARA_PLATFORM_CONTROL_URL="${PC_URL%/}"
  export EVIDARA_LEGAL_SEARCH_URL="${LS_URL%/}"

  eval "$(
    ./scripts/mint-cloud-run-tokens.sh
  )"
  PC_AUTH_HEADER=(-H "Authorization: Bearer ${EVIDARA_PLATFORM_CONTROL_TOKEN}")
fi

curl_json() {
  curl -fsS "${PC_AUTH_HEADER[@]}" "$@"
}

log() {
  printf '%s\n' "$*" >&2
}

# A Swiss federal-court docket, e.g. 1C_123/2024 (matches the provider's regex).
DOCKET_REGEX='[0-9]{1,2}[A-Z]?_[0-9]+/[0-9]{4}'
# Court hosts the provider is allowed to fetch from.
COURT_HOST_REGEX='bger\\.ch|bvger\\.ch|bstger\\.ch|bpger\\.ch|entscheidsuche\\.ch'

save_json() {
  local path="$1"
  cat >"${RUN_DIR}/${path}"
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

log "==> CH BGer/BVGer fast loop"
log "    environment=${ENVIRONMENT}"
log "    project=${PROJECT_ID}"
log "    region=${REGION}"
log "    template=${TEMPLATE_ID}"
log "    run_mode=${RUN_MODE}"
log "    authority=${AUTHORITY_ID}"
log "    max_resources=${MAX_RESOURCES}"
log "    max_polls=${MAX_POLLS}"
log "    poll_interval=${POLL_INTERVAL}"
log "    run_dir=${RUN_DIR}"

if [[ "${DRY_RUN}" -eq 1 ]]; then
  log "==> Dry run: stopping before API writes"
  exit 0
fi

curl_json "${PC_URL}/health" | save_json "platform-control-health.json"

VERSION_LABEL="ch-bger-fast-loop-$(date -u +%Y%m%dT%H%M%SZ)"
SOURCE_NAME="CH federal court decisions fast-loop source"
CREATE_PAYLOAD="$(jq -n \
  --arg version_label "${VERSION_LABEL}" \
  --arg template_id "${TEMPLATE_ID}" \
  --arg source_name "${SOURCE_NAME}" \
  --arg authority_id "${AUTHORITY_ID}" '{
  source: {
    name: $source_name,
    jurisdiction_id: "jur_ch_federal",
    authority_id: $authority_id,
    source_type: "website",
    document_family: "case_law"
  },
  source_version: {
    version_label: $version_label,
    overlay_id: "ch",
    provider_template_id: $template_id
  }
}')"

resolve_fast_loop_source \
  "${PC_URL}" "${SOURCE_NAME}" "${RUN_DIR}" \
  "${VERSION_LABEL}" "${TEMPLATE_ID}" "ch" "${CREATE_PAYLOAD}"

log "==> Checking readiness"
curl_json "${PC_URL}/v1/runs/readiness?source_id=${SOURCE_ID}&source_version_id=${SOURCE_VERSION_ID}&mode=${RUN_MODE}" | tee "${RUN_DIR}/readiness.json" >/dev/null
READY="$(jq -r '.ready' < "${RUN_DIR}/readiness.json")"
if [[ "${READY}" != "true" ]]; then
  echo "error: readiness returned ready=${READY}" >&2
  echo "note: ch_court_decisions is readiness=awaiting_evidence — implemented, but no" >&2
  echo "      acceptance evidence captured yet. Re-run with --mode acceptance to capture" >&2
  echo "      it; the lock refuses --mode preview for a provider awaiting evidence (#743)." >&2
  cat "${RUN_DIR}/readiness.json" >&2
  exit 1
fi

log "==> Approving source version"
curl -fsS -X POST "${PC_URL}/v1/versions/${SOURCE_VERSION_ID}/approve" \
  "${PC_AUTH_HEADER[@]}" | tee "${RUN_DIR}/approve.json" >/dev/null

RUN_PAYLOAD="$(jq -n --arg source_id "${SOURCE_ID}" --arg source_version_id "${SOURCE_VERSION_ID}" --arg run_mode "${RUN_MODE}" --argjson max_resources "${MAX_RESOURCES}" '{
  source_id: $source_id,
  source_version_id: $source_version_id,
  mode: $run_mode,
  scope: {
    kind: "discovered_subset",
    max_resources: $max_resources
  }
}')"

log "==> Launching preview run"
curl -fsS -X POST "${PC_URL}/v1/runs" \
  "${PC_AUTH_HEADER[@]}" \
  -H "Content-Type: application/json" \
  -d "${RUN_PAYLOAD}" | tee "${RUN_DIR}/run-create.json" >/dev/null

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

content_type_count="$(jq -r '[.content_type_breakdown[]? | select(.content_type=="text/html") | .count] | add // 0' < "${RUN_DIR}/preview-summary.json")"
captured_count="$(jq -r '.captured_resources_count // (.data | length) // 0' < "${RUN_DIR}/preview-summary.json")"
raw_artifact_count="$(jq -r '.total // (.data | length) // 0' < "${RUN_DIR}/raw-artifacts.json")"
title_ok="$(jq -r '[.data[]? | select((.title // "") | test(".+"))] | length' < "${RUN_DIR}/captured-resources.json")"
court_host_ok="$(jq -r --arg host_regex "${COURT_HOST_REGEX}" '[.data[]? | select((.final_url // "") | test($host_regex))] | length' < "${RUN_DIR}/captured-resources.json")"
docket_ok="$(jq -r --arg docket_regex "${DOCKET_REGEX}" '[.data[]? | select(
  ((.artifact_metadata.inline_body // "") | test($docket_regex))
  or ((.artifact_metadata.body // "") | test($docket_regex))
  or ((.artifact_metadata.provider_metadata.inline_body // "") | test($docket_regex))
  or ((.artifact_metadata.provider_metadata.body // "") | test($docket_regex))
)] | length' < "${RUN_DIR}/raw-artifacts.json")"
accepted_count="$(jq -r '[.data[]? | select(.status=="accepted")] | length' < "${RUN_DIR}/processing-status.json")"
processing_count="$(jq -r '[.data[]? | select(.status=="processing")] | length' < "${RUN_DIR}/processing-status.json")"
canonical_ready_count="$(jq -r '[.data[]? | select(.status=="canonical_ready")] | length' < "${RUN_DIR}/processing-status.json")"
processed_count="$(jq -r '[.data[]? | select(.event_type=="document.processed")] | length' < "${RUN_DIR}/document-lifecycle.json")"

# --- Content quality gates ---

# Decision markers: at least 2 occurrences of "Erwägung"/"E." across raw artifacts.
decision_marker_count="$(jq -r '[.data[]? |
  ((.artifact_metadata.inline_body // "") + (.artifact_metadata.body // "") +
   (.artifact_metadata.provider_metadata.inline_body // "") + (.artifact_metadata.provider_metadata.body // ""))
] | map([ match("Erwägung|Bundesgericht|Urteil"; "g") ] | length) | add // 0' < "${RUN_DIR}/raw-artifacts.json")"
decision_marker_ok=$(( decision_marker_count >= 2 ? 1 : 0 ))

# Minimum content length: at least 4 KB (4096 bytes) in the largest artifact body.
body_max_length="$(jq -r '[.data[]? |
  [(.artifact_metadata.inline_body // "" | length),
   (.artifact_metadata.body // "" | length),
   (.artifact_metadata.provider_metadata.inline_body // "" | length),
   (.artifact_metadata.provider_metadata.body // "" | length)] | max
] | max // 0' < "${RUN_DIR}/raw-artifacts.json")"
min_content_length_ok=$(( body_max_length >= 4096 ? 1 : 0 ))

verdict="pass"
if [[ "${content_type_count}" -lt 1 || "${captured_count}" -lt 1 || "${raw_artifact_count}" -lt 1 ]]; then
  verdict="provider_failed"
elif [[ "${accepted_count}" -lt 1 || "${processing_count}" -lt 1 || "${canonical_ready_count}" -lt 1 || "${processed_count}" -lt 1 ]]; then
  verdict="downstream_failed"
elif [[ "${title_ok}" -lt 1 || "${court_host_ok}" -lt 1 || "${docket_ok}" -lt 1 ]]; then
  verdict="pipeline_pass_content_suspect"
elif [[ "${decision_marker_ok}" -lt 1 || "${min_content_length_ok}" -lt 1 ]]; then
  verdict="pipeline_pass_content_suspect"
fi

SUMMARY_JSON="$(jq -n \
  --arg environment "${ENVIRONMENT}" \
  --arg run_mode "${RUN_MODE}" \
  --arg template_id "${TEMPLATE_ID}" \
  --arg authority_id "${AUTHORITY_ID}" \
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
  --argjson content_type_html_count "${content_type_count}" \
  --argjson accepted_count "${accepted_count}" \
  --argjson processing_count "${processing_count}" \
  --argjson canonical_ready_count "${canonical_ready_count}" \
  --argjson processed_count "${processed_count}" \
  --argjson title_ok "${title_ok}" \
  --argjson court_host_ok "${court_host_ok}" \
  --argjson docket_ok "${docket_ok}" \
  --argjson decision_marker_count "${decision_marker_count}" \
  --argjson decision_marker_ok "${decision_marker_ok}" \
  --argjson body_max_length "${body_max_length}" \
  --argjson min_content_length_ok "${min_content_length_ok}" \
  '{
    environment: $environment,
    run_mode: $run_mode,
    template_id: $template_id,
    authority_id: $authority_id,
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
      court_host_ok: $court_host_ok,
      docket_ok: $docket_ok,
      decision_marker_count: $decision_marker_count,
      decision_marker_ok: $decision_marker_ok,
      body_max_length: $body_max_length,
      min_content_length_ok: $min_content_length_ok
    }
  }')"

printf '%s\n' "${SUMMARY_JSON}" > "${RUN_DIR}/summary.json"
render_fast_loop_evidence_markdown "${RUN_DIR}/summary.json" "${RUN_DIR}/evidence-summary.md" "CH BGer/BVGer"

if [[ "${JSON_OUTPUT}" -eq 1 ]]; then
  cat "${RUN_DIR}/summary.json"
else
  log "==> Summary"
  jq . < "${RUN_DIR}/summary.json" >&2
  log "==> Evidence markdown"
  cat "${RUN_DIR}/evidence-summary.md" >&2
  if [[ "${KEEP_SOURCE}" -eq 0 ]]; then
    log "==> Acceptance source (stable, reused across runs): source_id=${SOURCE_ID} source_version_id=${SOURCE_VERSION_ID}"
  fi
fi

if [[ "${COPY_EVIDENCE}" -eq 1 ]]; then
  evidence_dest="$(copy_evidence_to_repo "${RUN_DIR}/summary.json" "${RUN_DIR}/evidence-summary.md" "ch-bger")"
  log "==> Evidence copied to ${evidence_dest}"
fi

if [[ "${verdict}" != "pass" ]]; then
  exit 1
fi
