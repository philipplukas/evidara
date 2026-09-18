#!/usr/bin/env bash
set -euo pipefail

SCRIPT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
# shellcheck source=scripts/fast-loop-evidence.sh
source "${SCRIPT_DIR}/fast-loop-evidence.sh"

ENVIRONMENT="dev"
TEMPLATE_ID="ris_ogd_bundesrecht_narrow_html"
JURISDICTION_ID="jur_at_federal"
AUTHORITY_ID="auth_ris"
AUTHORITY_ID_EXPLICIT=0
MAX_RESOURCES=5
KEEP_SOURCE=0
JSON_OUTPUT=0
DRY_RUN=0
MAX_POLLS=60
POLL_INTERVAL=5
WORKDIR_ROOT="${TMPDIR:-/tmp}/at-ris-fast-loop"
RUN_DIR=""
SOURCE_ID=""
SOURCE_VERSION_ID=""
RUN_ID=""
STARTED_AT_UTC="$(date -u +%Y-%m-%dT%H:%M:%SZ)"
# Operator API key for the self-hosted (Hetzner) runtime. When set, the loop skips
# gcloud/Cloud-Run identity-token minting and authenticates with `X-API-Key` against
# an explicit `--pc-url`. See scripts/ch-fedlex-fast-loop.sh and ADR-0029.
PC_API_KEY="${EVIDARA_PLATFORM_CONTROL_API_KEY:-}"

usage() {
  cat <<'EOF'
Usage: scripts/at-ris-fast-loop.sh [options]

Run a narrow AT RIS preview against platform-control and verify:
  - RIS HTML capture
  - DI accepted / processing / canonical_ready
  - document.processed lifecycle
  - minimum Austrian legal-text quality gates

Options:
  --env <dev|staging|prod>       Target environment (default: dev)
  --project <id>                 GCP project override
  --region <region>              Cloud Run region override
  --impersonate-sa <email>       Service account override
  --pc-url <url>                 Platform-control URL override
  --api-key <key>                Operator X-API-Key (self-hosted / Hetzner mode).
                                 When set, skips gcloud + Cloud-Run token minting and
                                 authenticates with X-API-Key against --pc-url.
                                 Also read from EVIDARA_PLATFORM_CONTROL_API_KEY.
  --template <template-id>       Source blueprint template (default: ris_ogd_bundesrecht_narrow_html)
  --jurisdiction-id <id>         Jurisdiction ID override (default: jur_at_federal)
  --authority-id <id>            Authority ID override (default: auto-detect live RIS authority, preferring auth_ris)
  --max-resources <n>            Preview scope max_resources (default: 5)
  --widen-discovery              Shortcut: --template firecrawl_justice_portal --max-resources 25
                                 Executes the AT discovery-widening slice from
                                 docs/runbooks/ch-at-thin-slice-execution.md.
  --max-polls <n>                Maximum run polls (default: 60)
  --poll-interval <seconds>      Run poll interval (default: 5)
  --out-dir <path>               Exact directory for persisted evidence bundle
  --json                         Emit final machine-readable summary JSON
  --dry-run                      Print resolved settings and exit before mutating APIs
  --keep-source                  Suppress the acceptance-source note. The source is stable and
                                 reused across runs (#766); there is nothing to clean up.
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
    --jurisdiction-id)
      JURISDICTION_ID="${2:?missing value for --jurisdiction-id}"
      shift 2
      ;;
    --authority-id)
      AUTHORITY_ID="${2:?missing value for --authority-id}"
      AUTHORITY_ID_EXPLICIT=1
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
      # An argv value is readable by any local user for the life of the process:
      # `ps -eo cmd` and /proc/<pid>/cmdline both show it, and so does any tool
      # that snapshots the process table. The key then survives in shell history
      # and in the scrollback of whatever ran this. EVIDARA_PLATFORM_CONTROL_API_KEY
      # has neither problem, so warn rather than accept silently.
      echo "warning: --api-key puts the key in this process's argv, where any local" >&2
      echo "         user can read it via \`ps\` or /proc. Prefer:" >&2
      echo "           export EVIDARA_PLATFORM_CONTROL_API_KEY=...  # then omit --api-key" >&2
      PC_API_KEY="${2:?missing value for --api-key}"
      shift 2
      ;;
    --max-resources)
      MAX_RESOURCES="${2:?missing value for --max-resources}"
      shift 2
      ;;
    --widen-discovery)
      TEMPLATE_ID="firecrawl_justice_portal"
      MAX_RESOURCES=25
      shift
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

require_cmd curl
require_cmd jq

mkdir -p "${WORKDIR_ROOT}"
if [[ -z "${RUN_DIR}" ]]; then
  RUN_DIR="${WORKDIR_ROOT}/$(date -u +%Y%m%dT%H%M%SZ)"
fi
mkdir -p "${RUN_DIR}"

# Auth header args reused by every platform-control call.
PC_AUTH_HEADER=()

if [[ -n "${PC_API_KEY}" ]]; then
  # Self-hosted (Hetzner) mode: X-API-Key against an explicit platform-control URL —
  # typically a `kubectl port-forward` to svc/platform-control-api. No gcloud, no SA,
  # no Cloud-Run token minting.
  if [[ -z "${EVIDARA_PLATFORM_CONTROL_URL:-}" ]]; then
    echo "error: self-hosted mode (--api-key) requires --pc-url / EVIDARA_PLATFORM_CONTROL_URL." >&2
    exit 1
  fi
  PROJECT_ID="self-hosted"
  REGION="self-hosted"
  PC_URL="${EVIDARA_PLATFORM_CONTROL_URL%/}"
  export EVIDARA_PLATFORM_CONTROL_URL="${PC_URL}"
  PC_AUTH_HEADER=(-H "X-API-Key: ${PC_API_KEY}")
else
  # Managed (GCP Cloud Run) mode: impersonated identity token as a Bearer credential.
  # ADR-0029 retired this runtime — the branch survives only so an operator with a
  # still-running Cloud Run deployment is not stranded. See #799.
  require_cmd gcloud

  PROJECT_ID="${GCP_PROJECT_ID:-project-dacd6b7b-dc96-4534-b82}"
  REGION="${GCP_REGION:-europe-west6}"
  SA="${EVIDARA_GCP_IMPERSONATE_SERVICE_ACCOUNT:-}"

  if [[ -z "${SA}" ]]; then
    echo "error: set EVIDARA_GCP_IMPERSONATE_SERVICE_ACCOUNT (or pass --api-key for self-hosted)." >&2
    exit 1
  fi

  PC_URL="${EVIDARA_PLATFORM_CONTROL_URL:-$(gcloud run services describe "platform-control-api-${ENVIRONMENT}" --project "${PROJECT_ID}" --region "${REGION}" --format='value(status.url)')}"

  export EVIDARA_GCP_IMPERSONATE_SERVICE_ACCOUNT="${SA}"
  export EVIDARA_PLATFORM_CONTROL_URL="${PC_URL%/}"

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

resolve_authority_id() {
  local authorities_json resolved_by_id resolved_by_slug resolved_by_name
  authorities_json="$(curl_json "${PC_URL}/v1/reference-data/authorities")"
  printf '%s\n' "${authorities_json}" > "${RUN_DIR}/authorities.json"

  resolved_by_id="$(jq -r \
    --arg authority_id "${AUTHORITY_ID}" \
    --arg jurisdiction_id "${JURISDICTION_ID}" \
    '.data[]? | select(.authority_id == $authority_id and .jurisdiction_id == $jurisdiction_id) | .authority_id' \
    < "${RUN_DIR}/authorities.json" | head -n1)"
  if [[ -n "${resolved_by_id}" ]]; then
    printf '%s' "${resolved_by_id}"
    return 0
  fi

  resolved_by_slug="$(jq -r \
    --arg jurisdiction_id "${JURISDICTION_ID}" \
    '.data[]? | select(.jurisdiction_id == $jurisdiction_id and (.slug // "") == "ris") | .authority_id' \
    < "${RUN_DIR}/authorities.json" | head -n1)"
  if [[ -n "${resolved_by_slug}" ]]; then
    printf '%s' "${resolved_by_slug}"
    return 0
  fi

  resolved_by_name="$(jq -r \
    --arg jurisdiction_id "${JURISDICTION_ID}" \
    '.data[]? | select(.jurisdiction_id == $jurisdiction_id and ((.name // "") | test("Rechtsinformationssystem|\\bRIS\\b"; "i"))) | .authority_id' \
    < "${RUN_DIR}/authorities.json" | head -n1)"
  if [[ -n "${resolved_by_name}" ]]; then
    printf '%s' "${resolved_by_name}"
    return 0
  fi

  return 1
}

expected_title_regex() {
  case "${TEMPLATE_ID}" in
    ris_ogd_bundesrecht_narrow_html|ris_ogd_bundesrecht_small_batch_html)
      printf '%s' '(Bundesgesetz|Verordnung|Kundmachung|Gesetz)'
      ;;
    *)
      printf '%s' '.+'
      ;;
  esac
}

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

log "==> AT RIS fast loop"
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

if [[ "${AUTHORITY_ID_EXPLICIT}" -eq 0 ]]; then
  if RESOLVED_AUTHORITY_ID="$(resolve_authority_id)"; then
    if [[ "${RESOLVED_AUTHORITY_ID}" != "${AUTHORITY_ID}" ]]; then
      log "==> Resolved live AT RIS authority_id=${RESOLVED_AUTHORITY_ID} (from default ${AUTHORITY_ID})"
    fi
    AUTHORITY_ID="${RESOLVED_AUTHORITY_ID}"
  else
    log "==> Could not auto-resolve live RIS authority_id for jurisdiction_id=${JURISDICTION_ID}; using ${AUTHORITY_ID}"
  fi
fi

VERSION_LABEL="at-ris-fast-loop-$(date -u +%Y%m%dT%H%M%SZ)"
SOURCE_NAME="AT RIS fast-loop source"
CREATE_PAYLOAD="$(jq -n \
  --arg version_label "${VERSION_LABEL}" \
  --arg template_id "${TEMPLATE_ID}" \
  --arg jurisdiction_id "${JURISDICTION_ID}" \
  --arg authority_id "${AUTHORITY_ID}" \
  --arg source_name "${SOURCE_NAME}" \
  '{
    source: {
      name: $source_name,
      jurisdiction_id: $jurisdiction_id,
      authority_id: $authority_id,
      source_type: "api",
      document_family: "law"
    },
    source_version: {
      version_label: $version_label,
      overlay_id: "at",
      provider_template_id: $template_id
    }
  }')"

resolve_fast_loop_source \
  "${PC_URL}" "${SOURCE_NAME}" "${RUN_DIR}" \
  "${VERSION_LABEL}" "${TEMPLATE_ID}" "at" "${CREATE_PAYLOAD}"

# Approve BEFORE checking readiness, not after (#998).
#
# Production readiness requires an approved source version, and this script creates
# that version moments earlier — so asking first and approving second made
# `--mode production` exit 1 every time on a fresh source, with the lock reporting
# `acquisition_lock_open: true` beside it. The driver was asking a question whose
# answer it was about to change.
#
# Approval is a PRECONDITION of the readiness check, not a consequence of it. The
# check still runs and still refuses; it now runs against the state the run will
# actually have.
log "==> Approving source version"
curl -fsS -X POST "${PC_URL}/v1/versions/${SOURCE_VERSION_ID}/approve" \
  "${PC_AUTH_HEADER[@]}" | tee "${RUN_DIR}/approve.json" >/dev/null

log "==> Checking readiness"
curl_json "${PC_URL}/v1/runs/readiness?source_id=${SOURCE_ID}&source_version_id=${SOURCE_VERSION_ID}&mode=preview" | tee "${RUN_DIR}/readiness.json" >/dev/null
READY="$(jq -r '.ready' < "${RUN_DIR}/readiness.json")"
if [[ "${READY}" != "true" ]]; then
  echo "error: readiness returned ready=${READY}" >&2
  cat "${RUN_DIR}/readiness.json" >&2
  exit 1
fi

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
    "${PC_AUTH_HEADER[@]}" \
    -H "Content-Type: application/json" \
    -d "${RUN_PAYLOAD}" || true
)"
if [[ "${RUN_HTTP_CODE}" != "200" && "${RUN_HTTP_CODE}" != "201" ]]; then
  echo "error: run creation failed with HTTP ${RUN_HTTP_CODE:-000}" >&2
  if [[ -s "${RUN_DIR}/run-create.json" ]]; then
    cat "${RUN_DIR}/run-create.json" >&2
  else
    echo "No response body captured. This usually means the platform request timed out before returning a run_id." >&2
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

# Computed here, not with the content gates below, because the wait loop needs
# to know how many documents it is waiting FOR. See the break condition.
captured_count="$(jq -r '.captured_resources_count // (.data | length) // 0' < "${RUN_DIR}/preview-summary.json")"
log "==> Waiting for DI processing and lifecycle signals (${captured_count} captured)"
for i in $(seq 1 24); do
  curl_json "${PC_URL}/v1/runs/${RUN_ID}/processing-status" | tee "${RUN_DIR}/processing-status.json" >/dev/null
  curl_json "${PC_URL}/v1/runs/${RUN_ID}/document-lifecycle" | tee "${RUN_DIR}/document-lifecycle.json" >/dev/null
  canonical_ready_count="$(jq -r '[.data[]? | select(.status=="canonical_ready")] | length' < "${RUN_DIR}/processing-status.json")"
  processed_count="$(jq -r '[.data[]? | select(.event_type=="document.processed")] | length' < "${RUN_DIR}/document-lifecycle.json")"
  log "  di poll ${i}: canonical_ready=${canonical_ready_count}/${captured_count} processed=${processed_count}"
  # Wait for EVERY captured document, not the first. This used to break on
  # `canonical_ready > 0`, which sampled the pipeline mid-flight and let the
  # verdict below report `pass` over a partial delivery (#731).
  if [[ "${canonical_ready_count}" -ge "${captured_count}" && "${processed_count}" -gt 0 ]]; then
    break
  fi
  sleep 5
done

TITLE_REGEX="$(expected_title_regex)"
content_type_html_count="$(jq -r '[.content_type_breakdown[]? | select(.content_type=="text/html") | .count] | add // 0' < "${RUN_DIR}/preview-summary.json")"
raw_artifact_count="$(jq -r '.total // (.data | length) // 0' < "${RUN_DIR}/raw-artifacts.json")"
title_ok="$(jq -r --arg title_regex "${TITLE_REGEX}" '[.data[]? | select((.title // "") | test($title_regex; "i"))] | length' < "${RUN_DIR}/captured-resources.json")"
ris_html_ok="$(jq -r '[.data[]? | select((.final_url // "") | test("ris\\.bka\\.gv\\.at/Dokumente/Bundesnormen/.+\\.html$"))] | length' < "${RUN_DIR}/captured-resources.json")"
section_gate_ok="$(jq -r '[.data[]? | select(
  ((.artifact_metadata.inline_body // "") | test("(§\\s*1|Art\\.\\s*1)"))
  or ((.artifact_metadata.body // "") | test("(§\\s*1|Art\\.\\s*1)"))
  or ((.artifact_metadata.provider_metadata.inline_body // "") | test("(§\\s*1|Art\\.\\s*1)"))
  or ((.artifact_metadata.provider_metadata.body // "") | test("(§\\s*1|Art\\.\\s*1)"))
)] | length' < "${RUN_DIR}/raw-artifacts.json")"
accepted_count="$(jq -r '[.data[]? | select(.status=="accepted")] | length' < "${RUN_DIR}/processing-status.json")"
processing_count="$(jq -r '[.data[]? | select(.status=="processing")] | length' < "${RUN_DIR}/processing-status.json")"
canonical_ready_count="$(jq -r '[.data[]? | select(.status=="canonical_ready")] | length' < "${RUN_DIR}/processing-status.json")"
processed_count="$(jq -r '[.data[]? | select(.event_type=="document.processed")] | length' < "${RUN_DIR}/document-lifecycle.json")"

verdict="pass"
if [[ "${content_type_html_count}" -lt 1 || "${captured_count}" -lt 1 || "${raw_artifact_count}" -lt 1 ]]; then
  verdict="provider_failed"
elif [[ "${accepted_count}" -lt 1 || "${processing_count}" -lt 1 || "${canonical_ready_count}" -lt 1 || "${processed_count}" -lt 1 ]]; then
  verdict="downstream_failed"
elif [[ "${canonical_ready_count}" -lt "${captured_count}" ]]; then
  # Every captured document must reach canonical, not just one. Nothing compared
  # these two counts, so a run capturing 4 and canonicalising 1 reported `pass` —
  # and this bundle is the evidence an operator flips `enabled: true` on
  # (ADR-0030). #772 established "a partial failure is a failure" for titles; it
  # was never applied to document count (#731).
  verdict="downstream_incomplete"
elif [[ "${title_ok}" -lt 1 || "${ris_html_ok}" -lt 1 || "${section_gate_ok}" -lt 1 ]]; then
  verdict="pipeline_pass_content_suspect"
fi

SUMMARY_JSON="$(jq -n \
  --arg environment "${ENVIRONMENT}" \
  --arg run_mode "preview" \
  --arg template_id "${TEMPLATE_ID}" \
  --arg jurisdiction_id "${JURISDICTION_ID}" \
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
  --argjson content_type_html_count "${content_type_html_count}" \
  --argjson accepted_count "${accepted_count}" \
  --argjson processing_count "${processing_count}" \
  --argjson canonical_ready_count "${canonical_ready_count}" \
  --argjson processed_count "${processed_count}" \
  --argjson title_ok "${title_ok}" \
  --argjson ris_html_ok "${ris_html_ok}" \
  --argjson section_gate_ok "${section_gate_ok}" \
  '{
    run_mode: $run_mode,
    environment: $environment,
    template_id: $template_id,
    jurisdiction_id: $jurisdiction_id,
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
      ris_html_ok: $ris_html_ok,
      section_gate_ok: $section_gate_ok
    }
  }')"

printf '%s\n' "${SUMMARY_JSON}" > "${RUN_DIR}/summary.json"
render_fast_loop_evidence_markdown "${RUN_DIR}/summary.json" "${RUN_DIR}/evidence-summary.md" "AT RIS"

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

if [[ "${verdict}" != "pass" ]]; then
  exit 1
fi
