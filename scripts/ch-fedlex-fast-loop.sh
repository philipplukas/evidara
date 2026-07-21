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
MAX_POLLS=60
POLL_INTERVAL=5
WORKDIR_ROOT="${TMPDIR:-/tmp}/ch-fedlex-fast-loop"
RUN_DIR=""
# Corpus-shaped expectations (#744). The defaults below ARE the Fedlex canary that
# runs nightly — changing one changes what the nightly asserts. They are flags so
# that a non-Fedlex corpus (a municipal PDF source, say) is measured against its own
# shape rather than silently reported as `provider_failed` for not being Fedlex.
EXPECT_CONTENT_TYPE="text/html"
URL_PATTERN='fedlex\.admin\.ch/filestore/.+\.html$'
JURISDICTION_ID="jur_ch_federal"
AUTHORITY_ID="auth_fedlex"
SOURCE_NAME="CH Fedlex SPARQL fast-loop source"
CORPUS_SLUG="ch-fedlex"
CORPUS_LABEL="CH Fedlex"
# Which ADR-0030 keys the run needs. `preview` is the default so the Fedlex
# nightly asserts exactly what it always did. `acceptance` is the mode an
# operator uses for a provider whose readiness is `awaiting_evidence`: it reaches
# the live portal to PRODUCE the evidence, so it cannot require the keys that
# evidence justifies. The lock refuses `preview` for such a provider, which is
# why a municipal run needs this flag (#743).
RUN_MODE="preview"
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
  - capture of the expected content type (default text/html; see --expect-content-type)
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
  --expect-content-type <mime>   Content type the capture gate counts (default: text/html).
                                 A PDF corpus needs application/pdf, or the run reports
                                 provider_failed while working correctly (#744).
  --url-pattern <regex>          Regex the captured final_url must match
                                 (default: fedlex\.admin\.ch/filestore/.+\.html$)
  --jurisdiction-id <id>         jurisdiction_id for the created source (default: jur_ch_federal)
  --authority-id <id>            authority_id for the created source (default: auth_fedlex)
  --source-name <name>           name for the created source
                                 (default: "CH Fedlex SPARQL fast-loop source")
  --corpus-slug <slug>           Slug used in the --copy-evidence filename (default: ch-fedlex)
  --corpus-label <label>         Human corpus name in the evidence markdown (default: CH Fedlex)
  --mode <preview|acceptance|production>
                                 Run mode (default: preview). Use `acceptance` for a
                                 provider whose readiness is `awaiting_evidence` —
                                 `preview` is refused by the two-key lock there (#743).
  --max-resources <n>            Preview scope max_resources (default: 25)
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
    --expect-content-type)
      EXPECT_CONTENT_TYPE="${2:?missing value for --expect-content-type}"
      shift 2
      ;;
    --url-pattern)
      URL_PATTERN="${2:?missing value for --url-pattern}"
      shift 2
      ;;
    --jurisdiction-id)
      JURISDICTION_ID="${2:?missing value for --jurisdiction-id}"
      shift 2
      ;;
    --authority-id)
      AUTHORITY_ID="${2:?missing value for --authority-id}"
      shift 2
      ;;
    --source-name)
      SOURCE_NAME="${2:?missing value for --source-name}"
      shift 2
      ;;
    --corpus-slug)
      CORPUS_SLUG="${2:?missing value for --corpus-slug}"
      shift 2
      ;;
    --corpus-label)
      CORPUS_LABEL="${2:?missing value for --corpus-label}"
      shift 2
      ;;
    --mode)
      RUN_MODE="${2:?missing value for --mode}"
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

# `.+` is the catch-all above: it matches any non-empty title, so for an unknown
# template the title gate asserts nothing and still reports `title_ok=1`. That is
# exactly the failure mode this repo keeps paying for — a check that reports green
# because it never ran (#605 mapping copy, #675 drifted mapping, #713 mapping-less
# producer). Per #744 the skip has to be visible in the evidence, so every gate that
# can self-skip carries a companion `<gate>_checked` value. The skip does NOT change
# whether the gate blocks the verdict; it only stops a non-check being read as a pass.
title_gate_checked() {
  case "${TEMPLATE_ID}" in
    fedlex_sparql_constitution_de|fedlex_sparql_vwvg_de|fedlex_sparql_federal_law_batch_de)
      printf '%s' '1'
      ;;
    *)
      printf '%s' '0'
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
log "    expect_content_type=${EXPECT_CONTENT_TYPE}"
log "    url_pattern=${URL_PATTERN}"
log "    jurisdiction_id=${JURISDICTION_ID}"
log "    authority_id=${AUTHORITY_ID}"
log "    source_name=${SOURCE_NAME}"
log "    corpus_slug=${CORPUS_SLUG}"
log "    run_mode=${RUN_MODE}"
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
CREATE_PAYLOAD="$(jq -n \
  --arg version_label "${VERSION_LABEL}" \
  --arg template_id "${TEMPLATE_ID}" \
  --arg source_name "${SOURCE_NAME}" \
  --arg jurisdiction_id "${JURISDICTION_ID}" \
  --arg authority_id "${AUTHORITY_ID}" '{
  source: {
    name: $source_name,
    jurisdiction_id: $jurisdiction_id,
    authority_id: $authority_id,
    source_type: "api",
    document_family: "law"
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

log "==> Launching ${RUN_MODE} run"
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
title_checked="$(title_gate_checked)"
content_type_count="$(jq -r --arg expect_content_type "${EXPECT_CONTENT_TYPE}" '[.content_type_breakdown[]? | select(.content_type==$expect_content_type) | .count] | add // 0' < "${RUN_DIR}/preview-summary.json")"
captured_count="$(jq -r '.captured_resources_count // (.data | length) // 0' < "${RUN_DIR}/preview-summary.json")"
raw_artifact_count="$(jq -r '.total // (.data | length) // 0' < "${RUN_DIR}/raw-artifacts.json")"
title_ok="$(jq -r --arg title_regex "${TITLE_REGEX}" '[.data[]? | select((.title // "") | test($title_regex))] | length' < "${RUN_DIR}/captured-resources.json")"
url_pattern_ok="$(jq -r --arg url_pattern "${URL_PATTERN}" '[.data[]? | select((.final_url // "") | test($url_pattern))] | length' < "${RUN_DIR}/captured-resources.json")"
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
#
# It only runs for `_de` templates; for anything else it defaults to 1 and has
# always been reported as a pass it never earned. `body_lang_hint_checked` makes
# that visible (#744) without changing what blocks the verdict.
body_lang_hint_ok=1
body_lang_hint_checked=0
if [[ "${TEMPLATE_ID}" == *_de ]]; then
  body_lang_hint_checked=1
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
# Follows the #744 skip convention: `checked=0` with `ok=1` is a gate that did not
# run and is reported as skipped, never folded into the pass count. Only the loop
# below sets `checked=1`, and only then does `ok` mean anything (#772).
indexed_title_checked=0
indexed_title_ok=1
indexed_title_observed=""

if [[ -z "${expected_lang}" ]]; then
  # Skipped, not passed. `indexed_language_checked` used to be set to 1 here, which
  # reported a facet assertion that never happened — the same green-because-it-never-ran
  # defect as #605/#675/#713. Keep `_ok=1` so the skip does not newly block the verdict
  # (#744 changes visibility only); `_checked=0` is what tells the reader it did not run.
  log "==> Indexed-language gate: SKIPPED (not applicable) — template ${TEMPLATE_ID} has no language suffix"
  indexed_language_checked=0
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
    indexed_title_observed=""
    mismatches=0
    title_mismatches=0
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
      # Title, read back from the index rather than from the capture (#772). The
      # captured title was always correct in #771; the pipeline replaced it after.
      observed_title="$(jq -r '.title // "missing"' < "${RUN_DIR}/ls-document-${doc_id}.json")"
      indexed_title_observed="${indexed_title_observed}${indexed_title_observed:+,}${doc_id}=${observed_title}"
      if ! printf '%s' "${observed_title}" | grep -Eq "${TITLE_REGEX}"; then
        title_mismatches=$(( title_mismatches + 1 ))
        log "  title mismatch: ${doc_id} expected=/${TITLE_REGEX}/ observed=${observed_title}"
      fi
    done
    if [[ "${all_present}" -eq 1 ]]; then
      indexed_language_checked=1
      indexed_language_ok=$(( mismatches == 0 ? 1 : 0 ))
      # Only meaningful when a real regex was supplied; the `.+` catch-all asserts
      # nothing, which is what `title_gate_checked` already records.
      if [[ "${title_checked}" -eq 1 ]]; then
        indexed_title_checked=1
        indexed_title_ok=$(( title_mismatches == 0 ? 1 : 0 ))
      fi
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

# In-force gate (#633): the acquired consolidation must be in force as-of the
# run's selection date. The fedlex_sparql provider emits the selected
# consolidation's validity window under `provider_metadata` (in_force_from /
# in_force_until / in_force_at_selection). A future `in_force_from`, or an
# explicit `in_force_at_selection=false`, means the corpus would hold law not yet
# in force — the exact defect that let "Stand am 1. Januar 2029" through as
# title_ok=1. Fail-closed on those; a missing in_force_from is only a loud warn,
# since not every provider/document publishes applicability dates.
today_utc="$(date -u +%Y-%m-%d)"
in_force_from_present="$(jq -r '[.data[]? |
  (.artifact_metadata.provider_metadata // {}) |
  select((.in_force_from // "") != "")] | length' < "${RUN_DIR}/raw-artifacts.json")"
future_dated_count="$(jq -r --arg today "${today_utc}" '[.data[]? |
  (.artifact_metadata.provider_metadata // {}) |
  select((.in_force_from // "") != "" and (.in_force_from > $today))] | length' \
  < "${RUN_DIR}/raw-artifacts.json")"
not_in_force_count="$(jq -r '[.data[]? |
  (.artifact_metadata.provider_metadata // {}) |
  select(.in_force_at_selection == false)] | length' < "${RUN_DIR}/raw-artifacts.json")"
in_force_ok=$(( future_dated_count == 0 && not_in_force_count == 0 ? 1 : 0 ))
if [[ "${future_dated_count}" -gt 0 || "${not_in_force_count}" -gt 0 ]]; then
  log "==> IN-FORCE GATE FAILED: acquired law not in force as-of ${today_utc}"
  log "    future_dated_artifacts=${future_dated_count} not_in_force_artifacts=${not_in_force_count}"
  log "    A future consolidation was selected — see issue #633."
elif [[ "${in_force_from_present}" -lt 1 ]]; then
  log "==> IN-FORCE GATE: WARN — no in_force_from published on any artifact; temporal"
  log "    validity is unknown for this run (in-force state cannot be asserted)."
fi

# --- Skipped-gate ledger (#744) ---
#
# A gate that self-skipped must be reported as skipped, never folded into the pass
# count. Collect the names here so both the machine summary and the human evidence
# name them explicitly. `skipped_gates` being empty is itself the signal an operator
# wants before flipping `enabled: true` under ADR-0030: every gate actually ran.
skipped_gates=()
[[ "${title_checked}" -eq 1 ]] || skipped_gates+=("title_ok")
[[ "${body_lang_hint_checked}" -eq 1 ]] || skipped_gates+=("body_lang_hint_ok")
# indexed_language_checked=0 with _ok=1 is a genuine skip; with _ok=0 it is a
# fail-closed "could not evaluate", which the verdict already catches.
if [[ "${indexed_language_checked}" -eq 0 && "${indexed_language_ok}" -eq 1 ]]; then
  skipped_gates+=("indexed_language_ok")
fi
[[ "${indexed_title_checked}" -eq 1 ]] || skipped_gates+=("indexed_title_ok")
skipped_gates_json="$(jq -nc '$ARGS.positional' --args "${skipped_gates[@]+"${skipped_gates[@]}"}")"

if [[ "${#skipped_gates[@]}" -gt 0 ]]; then
  log "==> Gates NOT evaluated for template ${TEMPLATE_ID} — reported as skipped, not as passes (#744):"
  for skipped_gate in "${skipped_gates[@]}"; do
    log "    - ${skipped_gate}: skipped (not applicable)"
  done
fi

verdict="pass"
if [[ "${content_type_count}" -lt 1 || "${captured_count}" -lt 1 || "${raw_artifact_count}" -lt 1 ]]; then
  verdict="provider_failed"
elif [[ "${accepted_count}" -lt 1 || "${processing_count}" -lt 1 || "${canonical_ready_count}" -lt 1 || "${processed_count}" -lt 1 ]]; then
  verdict="downstream_failed"
elif [[ "${in_force_ok}" -lt 1 ]]; then
  verdict="acquired_law_not_in_force"
elif [[ "${title_ok}" -lt 1 || "${url_pattern_ok}" -lt 1 || "${art1_ok}" -lt 1 ]]; then
  verdict="pipeline_pass_content_suspect"
elif [[ "${art_density_ok}" -lt 1 || "${min_content_length_ok}" -lt 1 || "${lang_agreement_ok}" -lt 1 ]]; then
  verdict="pipeline_pass_content_suspect"
elif [[ "${indexed_title_checked}" -eq 1 && "${indexed_title_ok}" -lt 1 ]]; then
  # `title_ok` above reads the captured title; this reads the indexed one. #771 was
  # invisible to the first and obvious to the second (#772).
  verdict="pipeline_pass_content_suspect"
fi

SUMMARY_JSON="$(jq -n \
  --arg environment "${ENVIRONMENT}" \
  --arg template_id "${TEMPLATE_ID}" \
  --arg jurisdiction_id "${JURISDICTION_ID}" \
  --arg authority_id "${AUTHORITY_ID}" \
  --arg corpus_slug "${CORPUS_SLUG}" \
  --arg run_mode "${RUN_MODE}" \
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
  --arg expect_content_type "${EXPECT_CONTENT_TYPE}" \
  --arg url_pattern "${URL_PATTERN}" \
  --argjson content_type_match_count "${content_type_count}" \
  --argjson accepted_count "${accepted_count}" \
  --argjson processing_count "${processing_count}" \
  --argjson canonical_ready_count "${canonical_ready_count}" \
  --argjson processed_count "${processed_count}" \
  --argjson title_ok "${title_ok}" \
  --argjson title_checked "${title_checked}" \
  --argjson indexed_title_ok "${indexed_title_ok}" \
  --argjson indexed_title_checked "${indexed_title_checked}" \
  --arg indexed_title_observed "${indexed_title_observed}" \
  --argjson url_pattern_ok "${url_pattern_ok}" \
  --argjson art1_ok "${art1_ok}" \
  --argjson art_density_count "${art_density_count}" \
  --argjson art_density_ok "${art_density_ok}" \
  --argjson body_max_length "${body_max_length}" \
  --argjson min_content_length_ok "${min_content_length_ok}" \
  --argjson lang_agreement_ok "${lang_agreement_ok}" \
  --argjson body_lang_hint_ok "${body_lang_hint_ok}" \
  --argjson body_lang_hint_checked "${body_lang_hint_checked}" \
  --argjson skipped_gates "${skipped_gates_json}" \
  --argjson indexed_language_checked "${indexed_language_checked}" \
  --argjson indexed_language_ok "${indexed_language_ok}" \
  --arg indexed_language_expected "${expected_lang}" \
  --arg indexed_language_observed "${indexed_language_observed}" \
  --arg as_of_utc "${today_utc}" \
  --argjson in_force_from_present "${in_force_from_present}" \
  --argjson future_dated_count "${future_dated_count}" \
  --argjson not_in_force_count "${not_in_force_count}" \
  --argjson in_force_ok "${in_force_ok}" \
  '{
    environment: $environment,
    template_id: $template_id,
    jurisdiction_id: $jurisdiction_id,
    authority_id: $authority_id,
    corpus_slug: $corpus_slug,
    run_mode: $run_mode,
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
      expect_content_type: $expect_content_type,
      content_type_match_count: $content_type_match_count,
      url_pattern: $url_pattern,
      accepted_count: $accepted_count,
      processing_count: $processing_count,
      canonical_ready_count: $canonical_ready_count,
      processed_count: $processed_count,
      title_ok: $title_ok,
      title_checked: $title_checked,
      indexed_title_ok: $indexed_title_ok,
      indexed_title_checked: $indexed_title_checked,
      indexed_title_observed: $indexed_title_observed,
      url_pattern_ok: $url_pattern_ok,
      art1_ok: $art1_ok,
      art_density_count: $art_density_count,
      art_density_ok: $art_density_ok,
      body_max_length: $body_max_length,
      min_content_length_ok: $min_content_length_ok,
      lang_agreement_ok: $lang_agreement_ok,
      body_lang_hint_ok: $body_lang_hint_ok,
      body_lang_hint_checked: $body_lang_hint_checked,
      skipped_gates: $skipped_gates,
      indexed_language_expected: $indexed_language_expected,
      indexed_language_observed: $indexed_language_observed,
      indexed_language_checked: $indexed_language_checked,
      indexed_language_ok: $indexed_language_ok,
      as_of_utc: $as_of_utc,
      in_force_from_present: $in_force_from_present,
      future_dated_count: $future_dated_count,
      not_in_force_count: $not_in_force_count,
      in_force_ok: $in_force_ok
    }
  }')"

printf '%s\n' "${SUMMARY_JSON}" > "${RUN_DIR}/summary.json"
render_fast_loop_evidence_markdown "${RUN_DIR}/summary.json" "${RUN_DIR}/evidence-summary.md" "${CORPUS_LABEL}"

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
  evidence_dest="$(copy_evidence_to_repo "${RUN_DIR}/summary.json" "${RUN_DIR}/evidence-summary.md" "${CORPUS_SLUG}")"
  log "==> Evidence copied to ${evidence_dest}"
fi

if [[ "${verdict}" != "pass" ]]; then
  exit 1
fi
