#!/usr/bin/env bash
set -euo pipefail

# ── CH Fedlex compose e2e ──────────────────────────────────────────────────
# Proves the CH Fedlex admin→search loop end-to-end against a LOCAL docker compose
# stack (issue #533, Stream H):
#
#   create source → approve → preview run → DI processing → projection bridge →
#   searchable in legal-search
#
# Unlike scripts/ch-fedlex-fast-loop.sh (Cloud Run + gcloud/X-API-Key auth), this
# driver assumes the full stack is already up on localhost with NO auth, exactly as
# started by:
#
#   docker compose -f docker-compose.yml -f docker-compose.local.yml \
#     --profile apps --profile nats --profile minio up -d --wait
#
# with PLATFORM_CONTROL_EVENT_PUBLISHER_BACKEND=nats and
# PLATFORM_CONTROL_ARTIFACT_STORE_BACKEND=s3 so the real publish + projection path
# runs (di-consumer → NATS → projection-bridge → legal-search).
#
# It reuses the content-gate/verdict logic from ch-fedlex-fast-loop.sh and the
# evidence renderer from fast-loop-evidence.sh. Emits a verdict and exits nonzero on
# failure.
# ───────────────────────────────────────────────────────────────────────────

SCRIPT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
# shellcheck source=scripts/fast-loop-evidence.sh
source "${SCRIPT_DIR}/fast-loop-evidence.sh"

PC_URL="${EVIDARA_PLATFORM_CONTROL_URL:-http://localhost:8000}"
LS_URL="${EVIDARA_LEGAL_SEARCH_URL:-http://localhost:3102}"
TEMPLATE_ID="${TEMPLATE_ID:-fedlex_sparql_constitution_de}"
MAX_RESOURCES="${MAX_RESOURCES:-25}"
MAX_POLLS="${MAX_POLLS:-60}"
POLL_INTERVAL="${POLL_INTERVAL:-5}"
DI_MAX_POLLS="${DI_MAX_POLLS:-36}"
DI_POLL_INTERVAL="${DI_POLL_INTERVAL:-5}"
SEARCH_MAX_POLLS="${SEARCH_MAX_POLLS:-24}"
SEARCH_POLL_INTERVAL="${SEARCH_POLL_INTERVAL:-5}"
SEARCH_QUERY="${SEARCH_QUERY:-Bundesverfassung}"
WORKDIR_ROOT="${WORKDIR_ROOT:-${TMPDIR:-/tmp}/ch-fedlex-compose-e2e}"
RUN_DIR="${RUN_DIR:-}"
STARTED_AT_UTC="$(date -u +%Y-%m-%dT%H:%M:%SZ)"

usage() {
  cat <<'EOF'
Usage: scripts/ch-fedlex-compose-e2e.sh [options]

Drive the CH Fedlex admin→search loop against a local docker compose stack and
assert the processed document becomes searchable in legal-search.

Assumes the stack is already up on localhost with no auth (see file header).

Options:
  --pc-url <url>            platform-control base URL (default: http://localhost:8000)
  --ls-url <url>            legal-search base URL (default: http://localhost:3102)
  --template <template-id>  Source blueprint template (default: fedlex_sparql_constitution_de)
  --max-resources <n>       Preview scope max_resources (default: 25)
  --query <text>            legal-search query used for the searchable assertion
                            (default: Bundesverfassung)
  --out-dir <path>          Exact directory for the persisted evidence bundle
  -h, --help                Show this help

Env overrides: EVIDARA_PLATFORM_CONTROL_URL, EVIDARA_LEGAL_SEARCH_URL, TEMPLATE_ID,
MAX_RESOURCES, MAX_POLLS, POLL_INTERVAL, DI_MAX_POLLS, DI_POLL_INTERVAL,
SEARCH_MAX_POLLS, SEARCH_POLL_INTERVAL, SEARCH_QUERY, WORKDIR_ROOT, RUN_DIR.
EOF
}

while [[ $# -gt 0 ]]; do
  case "$1" in
    --pc-url) PC_URL="${2:?missing value for --pc-url}"; shift 2 ;;
    --ls-url) LS_URL="${2:?missing value for --ls-url}"; shift 2 ;;
    --template) TEMPLATE_ID="${2:?missing value for --template}"; shift 2 ;;
    --max-resources) MAX_RESOURCES="${2:?missing value for --max-resources}"; shift 2 ;;
    --query) SEARCH_QUERY="${2:?missing value for --query}"; shift 2 ;;
    --out-dir) RUN_DIR="${2:?missing value for --out-dir}"; shift 2 ;;
    -h|--help) usage; exit 0 ;;
    *) echo "Unknown argument: $1" >&2; usage >&2; exit 1 ;;
  esac
done

PC_URL="${PC_URL%/}"
LS_URL="${LS_URL%/}"

require_cmd() {
  command -v "$1" >/dev/null 2>&1 || { echo "error: missing command '$1'" >&2; exit 1; }
}
require_cmd curl
require_cmd jq

mkdir -p "${WORKDIR_ROOT}"
if [[ -z "${RUN_DIR}" ]]; then
  RUN_DIR="${WORKDIR_ROOT}/$(date -u +%Y%m%dT%H%M%SZ)"
fi
mkdir -p "${RUN_DIR}"

log() { printf '%s\n' "$*" >&2; }

# No auth against the local compose stack — plain curl with fail-on-error.
curl_json() { curl -fsS --connect-timeout 5 --max-time 60 "$@"; }

expected_title_regex() {
  case "${TEMPLATE_ID}" in
    fedlex_sparql_constitution_de) printf '%s' 'Bundesverfassung' ;;
    fedlex_sparql_vwvg_de) printf '%s' 'Verwaltungsverfahren' ;;
    fedlex_sparql_federal_law_batch_de) printf '%s' '(Bundesverfassung|Verwaltungsverfahren)' ;;
    *) printf '%s' '.+' ;;
  esac
}

# Fedlex publishes every act as DE/FR/IT expressions and the templates are
# per-language, so the template suffix IS the language the indexed document must
# carry on its `language` facet (#572).
expected_language() {
  case "${TEMPLATE_ID}" in
    *_de) printf '%s' 'de' ;;
    *_fr) printf '%s' 'fr' ;;
    *_it) printf '%s' 'it' ;;
    *) printf '%s' '' ;;
  esac
}

poll_terminal_run_status() {
  local status=""
  for i in $(seq 1 "${MAX_POLLS}"); do
    curl_json "${PC_URL}/v1/runs/${RUN_ID}" | tee "${RUN_DIR}/run-state.json" >/dev/null
    status="$(jq -r '.status // empty' < "${RUN_DIR}/run-state.json")"
    log "poll ${i}/${MAX_POLLS}: run status=${status}"
    if [[ "${status}" == "completed" || "${status}" == "failed" || "${status}" == "cancelled" ]]; then
      printf '%s' "${status}"
      return 0
    fi
    sleep "${POLL_INTERVAL}"
  done
  printf '%s' "${status}"
  return 0
}

log "==> CH Fedlex compose e2e"
log "    platform-control=${PC_URL}"
log "    legal-search=${LS_URL}"
log "    template=${TEMPLATE_ID}"
log "    max_resources=${MAX_RESOURCES}"
log "    search_query=${SEARCH_QUERY}"
log "    run_dir=${RUN_DIR}"

# ── 1. Health ──────────────────────────────────────────────────────────────
log "==> Health checks"
curl_json "${PC_URL}/health" > "${RUN_DIR}/platform-control-health.json" || { echo "error: platform-control health failed" >&2; exit 1; }
curl_json "${LS_URL}/health" >/dev/null || { echo "error: legal-search health failed" >&2; exit 1; }

# ── 2. Create source + version ─────────────────────────────────────────────
VERSION_LABEL="ch-fedlex-compose-e2e-$(date -u +%Y%m%dT%H%M%SZ)"
CREATE_PAYLOAD="$(jq -n --arg version_label "${VERSION_LABEL}" --arg template_id "${TEMPLATE_ID}" '{
  source: {
    name: "CH Fedlex compose e2e source",
    jurisdiction_id: "jur_ch_federal",
    authority_id: "auth_fedlex",
    source_type: "api",
    document_family: "law"
  },
  source_version: {
    version_label: $version_label,
    overlay_id: "ch",
    provider_template_id: $template_id
  }
}')"

log "==> Creating source + version"
curl_json -X POST "${PC_URL}/v1/sources/with-version" \
  -H "Content-Type: application/json" \
  -d "${CREATE_PAYLOAD}" | tee "${RUN_DIR}/create.json" >/dev/null

SOURCE_ID="$(jq -r '.source.source_id // .source.id // .source_id // empty' < "${RUN_DIR}/create.json")"
SOURCE_VERSION_ID="$(jq -r '.source_version.source_version_id // .source_version.id // .source_version_id // empty' < "${RUN_DIR}/create.json")"
if [[ -z "${SOURCE_ID}" || -z "${SOURCE_VERSION_ID}" ]]; then
  echo "error: source creation did not return source/source_version ids" >&2
  cat "${RUN_DIR}/create.json" >&2
  exit 1
fi
log "    source_id=${SOURCE_ID} source_version_id=${SOURCE_VERSION_ID}"

# ── 3. Readiness ───────────────────────────────────────────────────────────
log "==> Checking readiness"
curl_json "${PC_URL}/v1/runs/readiness?source_id=${SOURCE_ID}&source_version_id=${SOURCE_VERSION_ID}&mode=preview" \
  | tee "${RUN_DIR}/readiness.json" >/dev/null
READY="$(jq -r '.ready' < "${RUN_DIR}/readiness.json")"
if [[ "${READY}" != "true" ]]; then
  echo "error: readiness returned ready=${READY}" >&2
  cat "${RUN_DIR}/readiness.json" >&2
  exit 1
fi

# ── 4. Approve ─────────────────────────────────────────────────────────────
log "==> Approving source version"
curl_json -X POST "${PC_URL}/v1/versions/${SOURCE_VERSION_ID}/approve" | tee "${RUN_DIR}/approve.json" >/dev/null

# ── 5. Launch preview run ──────────────────────────────────────────────────
RUN_PAYLOAD="$(jq -n --arg source_id "${SOURCE_ID}" --arg source_version_id "${SOURCE_VERSION_ID}" --argjson max_resources "${MAX_RESOURCES}" '{
  source_id: $source_id,
  source_version_id: $source_version_id,
  mode: "preview",
  scope: { kind: "discovered_subset", max_resources: $max_resources }
}')"

log "==> Launching preview run"
curl_json -X POST "${PC_URL}/v1/runs" \
  -H "Content-Type: application/json" \
  -d "${RUN_PAYLOAD}" | tee "${RUN_DIR}/run-create.json" >/dev/null

RUN_ID="$(jq -r '.run_id // .id // empty' < "${RUN_DIR}/run-create.json")"
if [[ -z "${RUN_ID}" ]]; then
  echo "error: run creation did not return run_id" >&2
  cat "${RUN_DIR}/run-create.json" >&2
  exit 1
fi
log "    run_id=${RUN_ID}"

FINAL_STATUS="$(poll_terminal_run_status)"
if [[ "${FINAL_STATUS}" != "completed" ]]; then
  echo "error: run finished with status=${FINAL_STATUS}" >&2
  cat "${RUN_DIR}/run-state.json" >&2
  exit 1
fi

# ── 6. Run diagnostics ─────────────────────────────────────────────────────
log "==> Collecting run diagnostics"
curl_json "${PC_URL}/v1/runs/${RUN_ID}/preview-summary" | tee "${RUN_DIR}/preview-summary.json" >/dev/null
curl_json "${PC_URL}/v1/runs/${RUN_ID}/captured-resources" | tee "${RUN_DIR}/captured-resources.json" >/dev/null
curl_json "${PC_URL}/v1/runs/${RUN_ID}/raw-artifacts" | tee "${RUN_DIR}/raw-artifacts.json" >/dev/null

# ── 7. Wait for DI processing + lifecycle ──────────────────────────────────
log "==> Waiting for DI canonical_ready + document.processed"
canonical_ready_count=0
processed_count=0
for i in $(seq 1 "${DI_MAX_POLLS}"); do
  curl_json "${PC_URL}/v1/runs/${RUN_ID}/processing-status" | tee "${RUN_DIR}/processing-status.json" >/dev/null
  curl_json "${PC_URL}/v1/runs/${RUN_ID}/document-lifecycle" | tee "${RUN_DIR}/document-lifecycle.json" >/dev/null
  canonical_ready_count="$(jq -r '[.data[]? | select(.status=="canonical_ready")] | length' < "${RUN_DIR}/processing-status.json")"
  processed_count="$(jq -r '[.data[]? | select(.event_type=="document.processed")] | length' < "${RUN_DIR}/document-lifecycle.json")"
  log "  di poll ${i}/${DI_MAX_POLLS}: canonical_ready=${canonical_ready_count} processed=${processed_count}"
  if [[ "${canonical_ready_count}" -gt 0 && "${processed_count}" -gt 0 ]]; then
    break
  fi
  sleep "${DI_POLL_INTERVAL}"
done

# ── 8. Assert searchable in legal-search ───────────────────────────────────
# The projection-bridge forwards document.processed into legal-search asynchronously,
# so poll the search endpoint until the doc is indexed.
log "==> Asserting searchable: GET ${LS_URL}/v1/search?q=${SEARCH_QUERY}"
search_hits=0
for i in $(seq 1 "${SEARCH_MAX_POLLS}"); do
  curl_json --get --data-urlencode "q=${SEARCH_QUERY}" "${LS_URL}/v1/search" \
    | tee "${RUN_DIR}/search.json" >/dev/null || true
  search_hits="$(jq -r '.totalResults // (.results | length) // 0' < "${RUN_DIR}/search.json" 2>/dev/null || echo 0)"
  log "  search poll ${i}/${SEARCH_MAX_POLLS}: totalResults=${search_hits}"
  if [[ "${search_hits}" =~ ^[0-9]+$ && "${search_hits}" -gt 0 ]]; then
    break
  fi
  sleep "${SEARCH_POLL_INTERVAL}"
done

# ── 8b. Assert the indexed language matches the acquired expression (#572) ──
# The search-facing `language` field is a facet and a filter: a wrong value is a
# wrong answer, not a missing one. Assert it on the documents THIS run produced.
EXPECTED_LANG="$(expected_language)"
indexed_language_ok=1
indexed_language_observed=""
if [[ -n "${EXPECTED_LANG}" ]]; then
  processed_document_ids="$(jq -r '[.data[]? | select(.event_type=="document.processed") | .document_id] | unique | join(" ")' < "${RUN_DIR}/document-lifecycle.json")"
  if [[ -z "${processed_document_ids}" ]]; then
    indexed_language_ok=0
  else
    log "==> Asserting indexed language=${EXPECTED_LANG} for: ${processed_document_ids}"
    read -ra doc_ids <<< "${processed_document_ids}"
    for doc_id in "${doc_ids[@]}"; do
      observed="missing"
      for i in $(seq 1 "${SEARCH_MAX_POLLS}"); do
        if curl_json "${LS_URL}/v1/documents/${doc_id}" > "${RUN_DIR}/ls-document-${doc_id}.json" 2>/dev/null; then
          observed="$(jq -r '.contentLanguage.display // "missing"' < "${RUN_DIR}/ls-document-${doc_id}.json")"
          break
        fi
        log "  language poll ${i}/${SEARCH_MAX_POLLS}: ${doc_id} not projected yet"
        sleep "${SEARCH_POLL_INTERVAL}"
      done
      indexed_language_observed="${indexed_language_observed}${indexed_language_observed:+,}${doc_id}=${observed}"
      if [[ "${observed}" != "${EXPECTED_LANG}" ]]; then
        indexed_language_ok=0
        log "  language mismatch: ${doc_id} expected=${EXPECTED_LANG} observed=${observed}"
      fi
    done
  fi
fi

# ── 9. Content gates (reused from ch-fedlex-fast-loop.sh) ───────────────────
TITLE_REGEX="$(expected_title_regex)"
content_type_count="$(jq -r '[.content_type_breakdown[]? | select(.content_type=="text/html") | .count] | add // 0' < "${RUN_DIR}/preview-summary.json")"
captured_count="$(jq -r '.captured_resources_count // (.data | length) // 0' < "${RUN_DIR}/preview-summary.json")"
raw_artifact_count="$(jq -r '.total // (.data | length) // 0' < "${RUN_DIR}/raw-artifacts.json")"
title_ok="$(jq -r --arg title_regex "${TITLE_REGEX}" '[.data[]? | select((.title // "") | test($title_regex))] | length' < "${RUN_DIR}/captured-resources.json")"
accepted_count="$(jq -r '[.data[]? | select(.status=="accepted")] | length' < "${RUN_DIR}/processing-status.json")"
processing_count="$(jq -r '[.data[]? | select(.status=="processing")] | length' < "${RUN_DIR}/processing-status.json")"

# ── 10. Verdict ────────────────────────────────────────────────────────────
verdict="pass"
if [[ "${content_type_count}" -lt 1 || "${captured_count}" -lt 1 || "${raw_artifact_count}" -lt 1 ]]; then
  verdict="provider_failed"
elif [[ "${accepted_count}" -lt 1 || "${canonical_ready_count}" -lt 1 || "${processed_count}" -lt 1 ]]; then
  verdict="downstream_failed"
elif [[ ! "${search_hits}" =~ ^[0-9]+$ || "${search_hits}" -lt 1 ]]; then
  # The whole point of Stream H: DI output must reach legal-search via the
  # projection-bridge and be searchable.
  verdict="search_failed"
elif [[ "${title_ok}" -lt 1 || "${indexed_language_ok}" -lt 1 ]]; then
  verdict="pipeline_pass_content_suspect"
fi

SUMMARY_JSON="$(jq -n \
  --arg template_id "${TEMPLATE_ID}" \
  --arg jurisdiction_id "jur_ch_federal" \
  --arg authority_id "auth_fedlex" \
  --arg source_id "${SOURCE_ID}" \
  --arg source_version_id "${SOURCE_VERSION_ID}" \
  --arg run_id "${RUN_ID}" \
  --arg verdict "${verdict}" \
  --arg run_dir "${RUN_DIR}" \
  --arg search_query "${SEARCH_QUERY}" \
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
  --argjson search_hits "${search_hits}" \
  --argjson indexed_language_ok "${indexed_language_ok}" \
  --arg indexed_language_expected "${EXPECTED_LANG}" \
  --arg indexed_language_observed "${indexed_language_observed}" \
  '{
    environment: "compose-local",
    template_id: $template_id,
    jurisdiction_id: $jurisdiction_id,
    authority_id: $authority_id,
    source_id: $source_id,
    source_version_id: $source_version_id,
    run_id: $run_id,
    max_resources: $max_resources,
    verdict: $verdict,
    run_dir: $run_dir,
    search_query: $search_query,
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
      search_hits: $search_hits,
      indexed_language_expected: $indexed_language_expected,
      indexed_language_observed: $indexed_language_observed,
      indexed_language_ok: $indexed_language_ok
    }
  }')"

printf '%s\n' "${SUMMARY_JSON}" > "${RUN_DIR}/summary.json"
render_fast_loop_evidence_markdown "${RUN_DIR}/summary.json" "${RUN_DIR}/evidence-summary.md" "CH Fedlex compose e2e"

log "==> Summary"
jq . < "${RUN_DIR}/summary.json" >&2
log "==> Evidence markdown"
cat "${RUN_DIR}/evidence-summary.md" >&2

if [[ "${verdict}" != "pass" ]]; then
  echo "VERDICT: ${verdict} (FAIL)" >&2
  exit 1
fi
echo "VERDICT: pass" >&2
