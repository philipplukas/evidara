#!/usr/bin/env bash
set -euo pipefail

SCRIPT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
# shellcheck source=scripts/fast-loop-evidence.sh
source "${SCRIPT_DIR}/fast-loop-evidence.sh"

ENVIRONMENT="dev"
TEMPLATE_ID="fedlex_sparql_constitution_de"
MAX_RESOURCES=25
KEEP_SOURCE=0
JSON_OUTPUT=0
DRY_RUN=0
COPY_EVIDENCE=0
COPY_EVIDENCE=0
MAX_POLLS=60
POLL_INTERVAL=5
WORKDIR_ROOT="${TMPDIR:-/tmp}/ch-fedlex-fast-loop"
RUN_DIR=""
SOURCE_ID=""
SOURCE_VERSION_ID=""
RUN_ID=""
# Self-hosted (Hetzner) auth: when an operator X-API-Key is supplied (flag or env),
# the loop skips gcloud/Cloud-Run identity-token minting and authenticates with
# `X-API-Key` against an explicit `--pc-url`. See docs/setup/hetzner-ch-fedlex-canary.md.
PC_API_KEY="${EVIDARA_PLATFORM_CONTROL_API_KEY:-}"
STARTED_AT_UTC="$(date -u +%Y-%m-%dT%H:%M:%SZ)"

usage() {
  cat <<'EOF'
Usage: scripts/ch-fedlex-fast-loop.sh [options]

Run a narrow CH Fedlex preview against platform-control on Cloud Run and verify:
  - text/html capture
  - DI accepted / processing / canonical_ready
  - document.processed lifecycle
  - minimum content quality gates
  - the indexed `language` facet matches the template's language (needs a legal-search URL)

Options:
  --env <dev|staging|prod>       Target environment (default: dev)
  --project <id>                 GCP project override
  --region <region>              Cloud Run region override
  --impersonate-sa <email>       Service account override
  --pc-url <url>                 Platform-control URL override
  --ls-url <url>                 Legal-search URL override. Required in self-hosted mode for
                                 the indexed-language gate (auto-discovered on Cloud Run).
  --api-key <key>                Operator X-API-Key (self-hosted / Hetzner mode).
                                 When set, skips gcloud + Cloud-Run token minting and
                                 authenticates with X-API-Key against --pc-url.
                                 Also read from EVIDARA_PLATFORM_CONTROL_API_KEY.
  --template <template-id>       Source blueprint template (default: fedlex_sparql_constitution_de)
  --max-resources <n>            Preview scope max_resources (default: 25)
  --max-polls <n>                Maximum run polls (default: 60)
  --poll-interval <seconds>      Run poll interval (default: 5)
  --out-dir <path>               Exact directory for persisted evidence bundle
  --json                         Emit final machine-readable summary JSON
  --dry-run                      Print resolved settings and exit before mutating APIs
  --keep-source                  Do not report cleanup guidance as follow-up work
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
    --copy-evidence)
      COPY_EVIDENCE=1
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

# legal-search is public-by-default in self-hosted mode; on Cloud Run it needs the
# minted identity token. Used only by the indexed-language gate below.
LS_AUTH_HEADER=()
if [[ -n "${EVIDARA_LEGAL_SEARCH_TOKEN:-}" ]]; then
  LS_AUTH_HEADER=(-H "Authorization: Bearer ${EVIDARA_LEGAL_SEARCH_TOKEN}")
fi

curl_json() {
  curl -fsS "${PC_AUTH_HEADER[@]}" "$@"
}

curl_ls_json() {
  curl -fsS "${LS_AUTH_HEADER[@]}" "$@"
}

log() {
  printf '%s\n' "$*" >&2
}

# Language of the expression the template acquires. Fedlex publishes every act as
# DE/FR/IT expressions and the templates are per-language, so the template suffix
# IS the expected language of the indexed document (#572).
expected_language() {
  case "${TEMPLATE_ID}" in
    *_de) printf '%s' 'de' ;;
    *_fr) printf '%s' 'fr' ;;
    *_it) printf '%s' 'it' ;;
    *) printf '%s' '' ;;
  esac
}

expected_title_regex() {
  case "${TEMPLATE_ID}" in
    fedlex_sparql_constitution_de)
      printf '%s' 'Bundesverfassung'
      ;;
    fedlex_sparql_vwvg_de)
      printf '%s' 'Verwaltungsverfahren'
      ;;
    fedlex_sparql_federal_law_batch_de)
      printf '%s' '(Bundesverfassung|Verwaltungsverfahren)'
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

log "==> CH Fedlex fast loop"
log "    environment=${ENVIRONMENT}"
log "    project=${PROJECT_ID}"
log "    region=${REGION}"
log "    template=${TEMPLATE_ID}"
log "    max_resources=${MAX_RESOURCES}"
log "    max_polls=${MAX_POLLS}"
log "    poll_interval=${POLL_INTERVAL}"
log "    run_dir=${RUN_DIR}"

if [[ "${DRY_RUN}" -eq 1 ]]; then
  log "==> Dry run: stopping before API writes"
  exit 0
fi

curl_json "${PC_URL}/health" | save_json "platform-control-health.json"

VERSION_LABEL="ch-fedlex-fast-loop-$(date -u +%Y%m%dT%H%M%SZ)"
CREATE_PAYLOAD="$(jq -n --arg version_label "${VERSION_LABEL}" --arg template_id "${TEMPLATE_ID}" '{
  source: {
    name: "CH Fedlex SPARQL fast-loop source",
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
curl -fsS -X POST "${PC_URL}/v1/sources/with-version" \
  "${PC_AUTH_HEADER[@]}" \
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
  "${PC_AUTH_HEADER[@]}" | tee "${RUN_DIR}/approve.json" >/dev/null

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

TITLE_REGEX="$(expected_title_regex)"
content_type_count="$(jq -r '[.content_type_breakdown[]? | select(.content_type=="text/html") | .count] | add // 0' < "${RUN_DIR}/preview-summary.json")"
captured_count="$(jq -r '.captured_resources_count // (.data | length) // 0' < "${RUN_DIR}/preview-summary.json")"
raw_artifact_count="$(jq -r '.total // (.data | length) // 0' < "${RUN_DIR}/raw-artifacts.json")"
title_ok="$(jq -r --arg title_regex "${TITLE_REGEX}" '[.data[]? | select((.title // "") | test($title_regex))] | length' < "${RUN_DIR}/captured-resources.json")"
fedlex_html_ok="$(jq -r '[.data[]? | select((.final_url // "") | test("fedlex\\.admin\\.ch/filestore/.+\\.html$"))] | length' < "${RUN_DIR}/captured-resources.json")"
art1_ok="$(jq -r '[.data[]? | select(
  ((.artifact_metadata.inline_body // "") | test("Art\\. 1"))
  or ((.artifact_metadata.body // "") | test("Art\\. 1"))
  or ((.artifact_metadata.provider_metadata.inline_body // "") | test("Art\\. 1"))
  or ((.artifact_metadata.provider_metadata.body // "") | test("Art\\. 1"))
)] | length' < "${RUN_DIR}/raw-artifacts.json")"
accepted_count="$(jq -r '[.data[]? | select(.status=="accepted")] | length' < "${RUN_DIR}/processing-status.json")"
processing_count="$(jq -r '[.data[]? | select(.status=="processing")] | length' < "${RUN_DIR}/processing-status.json")"
canonical_ready_count="$(jq -r '[.data[]? | select(.status=="canonical_ready")] | length' < "${RUN_DIR}/processing-status.json")"
processed_count="$(jq -r '[.data[]? | select(.event_type=="document.processed")] | length' < "${RUN_DIR}/document-lifecycle.json")"

# --- Content quality gates ---

# Article density: at least 3 occurrences of "Art." across all raw artifacts
art_density_count="$(jq -r '[.data[]? |
  ((.artifact_metadata.inline_body // "") + (.artifact_metadata.body // "") +
   (.artifact_metadata.provider_metadata.inline_body // "") + (.artifact_metadata.provider_metadata.body // ""))
] | map([ match("Art\\."; "g") ] | length) | add // 0' < "${RUN_DIR}/raw-artifacts.json")"
art_density_ok=$(( art_density_count >= 3 ? 1 : 0 ))

# Minimum content length: at least 10 KB (10240 bytes) in the largest artifact body
body_max_length="$(jq -r '[.data[]? |
  [(.artifact_metadata.inline_body // "" | length),
   (.artifact_metadata.body // "" | length),
   (.artifact_metadata.provider_metadata.inline_body // "" | length),
   (.artifact_metadata.provider_metadata.body // "" | length)] | max
] | max // 0' < "${RUN_DIR}/raw-artifacts.json")"
min_content_length_ok=$(( body_max_length >= 10240 ? 1 : 0 ))

# Body-language hint: for German templates, the acquired body must read as German.
# NOTE: this only inspects the RAW artifact. It says nothing about the language the
# document is finally *indexed* with — it reported ok for the run in #572 while the
# search facet said `it`. Keep it as a cheap provider-side hint; the gate that
# actually protects the facet is `indexed_language_ok` below.
body_lang_hint_ok=1
if [[ "${TEMPLATE_ID}" == *_de ]]; then
  body_lang_hint_ok="$(jq -r '[.data[]? | select(
    ((.artifact_metadata.inline_body // "") | test("Abs\\.|Bund|Recht"))
    or ((.artifact_metadata.body // "") | test("Abs\\.|Bund|Recht"))
    or ((.artifact_metadata.provider_metadata.inline_body // "") | test("Abs\\.|Bund|Recht"))
    or ((.artifact_metadata.provider_metadata.body // "") | test("Abs\\.|Bund|Recht"))
  )] | if length > 0 then 1 else 0 end' < "${RUN_DIR}/raw-artifacts.json")"
fi

# Indexed language: the search-facing `language` facet of every document this run
# produced must equal the language of the expression the template acquired (#572).
# A wrong facet value is worse than a missing one — filtering "Swiss law, German"
# silently dropped the Federal Constitution while "Italian" surfaced it — so this
# gate is fail-closed: if it cannot be evaluated, the run is content-suspect.
expected_lang="$(expected_language)"
processed_document_ids="$(jq -r '[.data[]? | select(.event_type=="document.processed") | .document_id] | unique | join(" ")' < "${RUN_DIR}/document-lifecycle.json")"
indexed_language_checked=0
indexed_language_ok=0
indexed_language_observed=""

if [[ -z "${expected_lang}" ]]; then
  log "==> Indexed-language gate: template ${TEMPLATE_ID} has no language suffix — nothing to assert"
  indexed_language_checked=1
  indexed_language_ok=1
elif [[ -z "${LS_URL}" ]]; then
  log "==> Indexed-language gate: SKIPPED — no legal-search URL."
  log "    Pass --ls-url (self-hosted: kubectl -n evidara port-forward svc/legal-search-api 3102:3000)"
  log "    so the run can prove the search facet, not just the raw body."
elif [[ -z "${processed_document_ids}" ]]; then
  log "==> Indexed-language gate: no document.processed events to check"
else
  log "==> Asserting indexed language=${expected_lang} for: ${processed_document_ids}"
  read -ra doc_ids <<< "${processed_document_ids}"
  for attempt in $(seq 1 12); do
    indexed_language_observed=""
    mismatches=0
    all_present=1
    for doc_id in "${doc_ids[@]}"; do
      if ! curl_ls_json "${LS_URL}/v1/documents/${doc_id}" > "${RUN_DIR}/ls-document-${doc_id}.json" 2>/dev/null; then
        all_present=0
        break
      fi
      observed="$(jq -r '.contentLanguage.display // "missing"' < "${RUN_DIR}/ls-document-${doc_id}.json")"
      indexed_language_observed="${indexed_language_observed}${indexed_language_observed:+,}${doc_id}=${observed}"
      if [[ "${observed}" != "${expected_lang}" ]]; then
        mismatches=$(( mismatches + 1 ))
        log "  language mismatch: ${doc_id} expected=${expected_lang} observed=${observed}"
      fi
    done
    if [[ "${all_present}" -eq 1 ]]; then
      indexed_language_checked=1
      indexed_language_ok=$(( mismatches == 0 ? 1 : 0 ))
      break
    fi
    log "  indexed-language poll ${attempt}/12: projection not queryable yet"
    sleep 5
  done

  if [[ "${indexed_language_checked}" -ne 1 ]]; then
    log "  indexed-language gate could not read the projection from legal-search"
  fi
fi

# Kept for continuity with older evidence bundles: the language verdict is now the
# AND of the raw-body hint and the indexed facet, so a `1` here means both.
lang_agreement_ok=$(( body_lang_hint_ok == 1 && indexed_language_ok == 1 ? 1 : 0 ))

verdict="pass"
if [[ "${content_type_count}" -lt 1 || "${captured_count}" -lt 1 || "${raw_artifact_count}" -lt 1 ]]; then
  verdict="provider_failed"
elif [[ "${accepted_count}" -lt 1 || "${processing_count}" -lt 1 || "${canonical_ready_count}" -lt 1 || "${processed_count}" -lt 1 ]]; then
  verdict="downstream_failed"
elif [[ "${title_ok}" -lt 1 || "${fedlex_html_ok}" -lt 1 || "${art1_ok}" -lt 1 ]]; then
  verdict="pipeline_pass_content_suspect"
elif [[ "${art_density_ok}" -lt 1 || "${min_content_length_ok}" -lt 1 || "${lang_agreement_ok}" -lt 1 ]]; then
  verdict="pipeline_pass_content_suspect"
fi

SUMMARY_JSON="$(jq -n \
  --arg environment "${ENVIRONMENT}" \
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
  --argjson content_type_html_count "${content_type_count}" \
  --argjson accepted_count "${accepted_count}" \
  --argjson processing_count "${processing_count}" \
  --argjson canonical_ready_count "${canonical_ready_count}" \
  --argjson processed_count "${processed_count}" \
  --argjson title_ok "${title_ok}" \
  --argjson fedlex_html_ok "${fedlex_html_ok}" \
  --argjson art1_ok "${art1_ok}" \
  --argjson art_density_count "${art_density_count}" \
  --argjson art_density_ok "${art_density_ok}" \
  --argjson body_max_length "${body_max_length}" \
  --argjson min_content_length_ok "${min_content_length_ok}" \
  --argjson lang_agreement_ok "${lang_agreement_ok}" \
  --argjson body_lang_hint_ok "${body_lang_hint_ok}" \
  --argjson indexed_language_checked "${indexed_language_checked}" \
  --argjson indexed_language_ok "${indexed_language_ok}" \
  --arg indexed_language_expected "${expected_lang}" \
  --arg indexed_language_observed "${indexed_language_observed}" \
  '{
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
      fedlex_html_ok: $fedlex_html_ok,
      art1_ok: $art1_ok,
      art_density_count: $art_density_count,
      art_density_ok: $art_density_ok,
      body_max_length: $body_max_length,
      min_content_length_ok: $min_content_length_ok,
      lang_agreement_ok: $lang_agreement_ok,
      body_lang_hint_ok: $body_lang_hint_ok,
      indexed_language_expected: $indexed_language_expected,
      indexed_language_observed: $indexed_language_observed,
      indexed_language_checked: $indexed_language_checked,
      indexed_language_ok: $indexed_language_ok
    }
  }')"

printf '%s\n' "${SUMMARY_JSON}" > "${RUN_DIR}/summary.json"
render_fast_loop_evidence_markdown "${RUN_DIR}/summary.json" "${RUN_DIR}/evidence-summary.md" "CH Fedlex"

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

if [[ "${COPY_EVIDENCE}" -eq 1 ]]; then
  evidence_dest="$(copy_evidence_to_repo "${RUN_DIR}/summary.json" "${RUN_DIR}/evidence-summary.md" "ch-fedlex")"
  log "==> Evidence copied to ${evidence_dest}"
fi

if [[ "${COPY_EVIDENCE}" -eq 1 ]]; then
  evidence_dest="$(copy_evidence_to_repo "${RUN_DIR}/summary.json" "${RUN_DIR}/evidence-summary.md" "ch-fedlex")"
  log "==> Evidence copied to ${evidence_dest}"
fi

if [[ "${verdict}" != "pass" ]]; then
  exit 1
fi
