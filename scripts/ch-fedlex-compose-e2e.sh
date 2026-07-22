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
#   PLATFORM_CONTROL_EVENT_PUBLISHER_BACKEND=nats \
#   PLATFORM_CONTROL_ARTIFACT_STORE_BACKEND=s3 \
#     docker compose -f docker-compose.yml -f docker-compose.local.yml \
#       --profile apps --profile nats --profile minio --profile search up -d --wait
#
# BOTH env vars are required, or the real publish path never runs: the defaults
# are `noop`/`local`, so platform-control captures the documents, reports the run
# `completed`, and publishes nothing. DI then sits idle and the harness times out
# waiting for a document that was never handed to it.
#
# `--profile search` is likewise REQUIRED, and was missing from this header until
# 2026-07-22. OpenSearch declares `profiles: [search, full, lean-stack]`, and
# `legal-search-api` (profile `apps`) depends on it, so without it compose refuses
# the whole project:
#
#   service "legal-search-api" depends on undefined service "opensearch":
#   invalid compose project
#
# Nothing starts at all, so that failure is loud rather than silent — but the
# command as documented could never have worked, which means nobody had run this
# harness from its own instructions.
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
# Overlay the template lives under. Hardcoded to "ch" until 2026-07-22, which
# made every --template outside the CH overlay 404 at source creation while the
# script advertised itself as template-parameterised (#798).
OVERLAY_ID="${OVERLAY_ID:-ch}"
MAX_RESOURCES="${MAX_RESOURCES:-25}"
MAX_POLLS="${MAX_POLLS:-60}"
POLL_INTERVAL="${POLL_INTERVAL:-5}"
DI_MAX_POLLS="${DI_MAX_POLLS:-36}"
DI_POLL_INTERVAL="${DI_POLL_INTERVAL:-5}"
SEARCH_MAX_POLLS="${SEARCH_MAX_POLLS:-24}"
SEARCH_POLL_INTERVAL="${SEARCH_POLL_INTERVAL:-5}"
SEARCH_QUERY="${SEARCH_QUERY:-Bundesverfassung}"
# Corpus-shaped expectations (#744). Defaults reproduce the Fedlex behaviour this
# script has always had; they are parameters so a non-HTML / non-federal corpus is
# measured against its own shape instead of being reported as `provider_failed`.
# (There is no --url-pattern or --corpus-slug here: this script has no final_url
# gate and no --copy-evidence path.)
EXPECT_CONTENT_TYPE="${EXPECT_CONTENT_TYPE:-text/html}"
JURISDICTION_ID="${JURISDICTION_ID:-jur_ch_federal}"
AUTHORITY_ID="${AUTHORITY_ID:-auth_fedlex}"
SOURCE_NAME="${SOURCE_NAME:-CH Fedlex compose e2e source}"
# See ch-fedlex-fast-loop.sh: `acceptance` is required for a provider whose
# readiness is `awaiting_evidence`, since the lock refuses `preview` there (#743).
RUN_MODE="${RUN_MODE:-preview}"
# Overrides the Fedlex `_de`/`_fr`/`_it` template-suffix convention. Set it for
# any corpus that does not follow that naming, or the indexed-language facet goes
# unverified while the run still reports `pass` (#735).
EXPECT_LANGUAGE="${EXPECT_LANGUAGE:-}"
# Regex the captured title must match. Without it the gate falls back to a
# per-template lookup that ends in a `.+` catch-all — which matches any non-empty
# title, so the gate reports `title_ok=1` having asserted nothing (#744).
EXPECT_TITLE="${EXPECT_TITLE:-}"
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
  --overlay <overlay-id>    Overlay the template lives under (default: ch).
                            Required for non-CH corpora — at, de, eu, fr.
  --expect-content-type <mime>
                            Content type the capture gate counts (default: text/html).
                            A PDF corpus needs application/pdf, or the run reports
                            provider_failed while working correctly (#744).
  --jurisdiction-id <id>    jurisdiction_id for the created source (default: jur_ch_federal)
  --authority-id <id>       authority_id for the created source (default: auth_fedlex)
  --source-name <name>      name for the created source
                            (default: "CH Fedlex compose e2e source")
  --mode <preview|acceptance|production>
                            Run mode (default: preview). Use `acceptance` for a
                            provider whose readiness is `awaiting_evidence` (#743).
  --expect-language <code>  Language the indexed document must carry (e.g. de).
                            Without it the gate derives from the Fedlex template
                            suffix and SELF-SKIPS for other corpora (#735).
  --expect-title <regex>    Regex the captured title must match. Without it the
                            gate falls back to a `.+` catch-all that asserts
                            nothing while reporting title_ok=1 (#744).
  --max-resources <n>       Preview scope max_resources (default: 25)
  --query <text>            legal-search query used for the searchable assertion
                            (default: Bundesverfassung)
  --out-dir <path>          Exact directory for the persisted evidence bundle
  -h, --help                Show this help

Env overrides: EVIDARA_PLATFORM_CONTROL_URL, EVIDARA_LEGAL_SEARCH_URL, TEMPLATE_ID,
EXPECT_CONTENT_TYPE, JURISDICTION_ID, AUTHORITY_ID, SOURCE_NAME, RUN_MODE, EXPECT_LANGUAGE, EXPECT_TITLE,
OVERLAY_ID, MAX_RESOURCES, MAX_POLLS, POLL_INTERVAL, DI_MAX_POLLS, DI_POLL_INTERVAL,
SEARCH_MAX_POLLS, SEARCH_POLL_INTERVAL, SEARCH_QUERY, WORKDIR_ROOT, RUN_DIR.
EOF
}

while [[ $# -gt 0 ]]; do
  case "$1" in
    --pc-url) PC_URL="${2:?missing value for --pc-url}"; shift 2 ;;
    --ls-url) LS_URL="${2:?missing value for --ls-url}"; shift 2 ;;
    --template) TEMPLATE_ID="${2:?missing value for --template}"; shift 2 ;;
    --overlay) OVERLAY_ID="${2:?missing value for --overlay}"; shift 2 ;;
    --expect-content-type) EXPECT_CONTENT_TYPE="${2:?missing value for --expect-content-type}"; shift 2 ;;
    --jurisdiction-id) JURISDICTION_ID="${2:?missing value for --jurisdiction-id}"; shift 2 ;;
    --authority-id) AUTHORITY_ID="${2:?missing value for --authority-id}"; shift 2 ;;
    --source-name) SOURCE_NAME="${2:?missing value for --source-name}"; shift 2 ;;
    --mode) RUN_MODE="${2:?missing value for --mode}"; shift 2 ;;
    --expect-language) EXPECT_LANGUAGE="${2:?missing value for --expect-language}"; shift 2 ;;
    --expect-title) EXPECT_TITLE="${2:?missing value for --expect-title}"; shift 2 ;;
    --max-resources) MAX_RESOURCES="${2:?missing value for --max-resources}"; shift 2 ;;
    --query) SEARCH_QUERY="${2:?missing value for --query}"; shift 2 ;;
    --out-dir) RUN_DIR="${2:?missing value for --out-dir}"; shift 2 ;;
    -h|--help) usage; exit 0 ;;
    *) echo "Unknown argument: $1" >&2; usage >&2; exit 1 ;;
  esac
done

case "${RUN_MODE}" in
  preview|acceptance|production) ;;
  *)
    echo "error: --mode must be preview, acceptance or production (got '${RUN_MODE}')" >&2
    exit 1
    ;;
esac

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
  if [[ -n "${EXPECT_TITLE}" ]]; then
    printf '%s' "${EXPECT_TITLE}"
    return
  fi
  case "${TEMPLATE_ID}" in
    fedlex_sparql_constitution_de) printf '%s' 'Bundesverfassung' ;;
    fedlex_sparql_vwvg_de) printf '%s' 'Verwaltungsverfahren' ;;
    fedlex_sparql_federal_law_batch_de) printf '%s' '(Bundesverfassung|Verwaltungsverfahren)' ;;
    *) printf '%s' '.+' ;;
  esac
}

# `.+` above is the catch-all: it matches any non-empty title, so for an unknown
# template the title gate asserts nothing and still reports `title_ok=1`. A check
# that reports green because it never ran is the failure mode this repo keeps paying
# for (#605, #675, #713), so per #744 every self-skipping gate carries a companion
# `<gate>_checked`. Visibility only — the skip does not change what blocks the verdict.
title_gate_checked() {
  if [[ -n "${EXPECT_TITLE}" ]]; then
    printf '%s' '1'
    return
  fi
  case "${TEMPLATE_ID}" in
    fedlex_sparql_constitution_de|fedlex_sparql_vwvg_de|fedlex_sparql_federal_law_batch_de)
      printf '%s' '1' ;;
    *) printf '%s' '0' ;;
  esac
}

# The language the indexed document must carry on its `language` facet (#572).
#
# `--expect-language` first, then the Fedlex template-suffix convention. Fedlex
# publishes every act as DE/FR/IT expressions with per-language templates, so
# there the suffix IS the language — but deriving ONLY from the suffix meant the
# gate silently self-skipped for every corpus that does not follow that naming,
# which is how the first municipal acceptance run reported `pass` with the facet
# unverified (#735 review). The template declares `language_codes`, so this is
# information the harness had all along and was not reading.
expected_language() {
  if [[ -n "${EXPECT_LANGUAGE}" ]]; then
    printf '%s' "${EXPECT_LANGUAGE}"
    return
  fi
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
log "    expect_content_type=${EXPECT_CONTENT_TYPE}"
log "    jurisdiction_id=${JURISDICTION_ID}"
log "    authority_id=${AUTHORITY_ID}"
log "    source_name=${SOURCE_NAME}"
log "    run_mode=${RUN_MODE}"
log "    expect_language=${EXPECT_LANGUAGE:-<from template suffix>}"
log "    expect_title=${EXPECT_TITLE:-<from template lookup>}"
log "    max_resources=${MAX_RESOURCES}"
log "    search_query=${SEARCH_QUERY}"
log "    run_dir=${RUN_DIR}"

# ── 1. Health ──────────────────────────────────────────────────────────────
log "==> Health checks"
curl_json "${PC_URL}/health" > "${RUN_DIR}/platform-control-health.json" || { echo "error: platform-control health failed" >&2; exit 1; }
curl_json "${LS_URL}/health" >/dev/null || { echo "error: legal-search health failed" >&2; exit 1; }

# ── 2. Create source + version ─────────────────────────────────────────────
VERSION_LABEL="ch-fedlex-compose-e2e-$(date -u +%Y%m%dT%H%M%SZ)"
CREATE_PAYLOAD="$(jq -n \
  --arg version_label "${VERSION_LABEL}" \
  --arg template_id "${TEMPLATE_ID}" \
  --arg overlay_id "${OVERLAY_ID}" \
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
    overlay_id: $overlay_id,
    provider_template_id: $template_id
  }
}')"

# Reuse the acceptance source for this template if one already exists (#766).
#
# `document_id` is derived from (tenant_id, corpus_id, source_id, upstream_locator)
# — `pipeline.py:166`. Minting a fresh source per run therefore minted a fresh
# DOCUMENT per run: the same ordinance indexed again, `document_revision: 1` on
# both, indistinguishable in search. The pipeline is right — re-acquiring under a
# *stable* source publishes the next revision, which is what `_document_identity_key`
# was built for (#652) — the harness was simply never stable.
#
# It also corrupted the harness's own evidence: `search_hits` is a gate, and a
# second run turned `1` into `2`, reading like broader coverage when it was one
# law counted twice. That is what made the first #751 evidence bundle wrong.
log "==> Resolving acceptance source"
curl_json "${PC_URL}/v1/sources?q=$(printf '%s' "${SOURCE_NAME}" | jq -sRr @uri)&limit=100" \
  | tee "${RUN_DIR}/source-lookup.json" >/dev/null
SOURCE_ID="$(jq -r --arg name "${SOURCE_NAME}" \
  'first(.data[]? | select(.name == $name) | .source_id // .id) // empty' \
  < "${RUN_DIR}/source-lookup.json")"

if [[ -n "${SOURCE_ID}" ]]; then
  log "    reusing source ${SOURCE_ID} — re-acquisition publishes the next revision"
  VERSION_PAYLOAD="$(jq -n \
    --arg version_label "${VERSION_LABEL}" \
    --arg overlay_id "${OVERLAY_ID}" \
    --arg template_id "${TEMPLATE_ID}" '{
    version_label: $version_label,
    overlay_id: $overlay_id,
    provider_template_id: $template_id
  }')"
  curl_json -X POST "${PC_URL}/v1/sources/${SOURCE_ID}/versions" \
    -H "Content-Type: application/json" \
    -d "${VERSION_PAYLOAD}" | tee "${RUN_DIR}/create.json" >/dev/null
  SOURCE_VERSION_ID="$(jq -r '.source_version_id // .id // empty' < "${RUN_DIR}/create.json")"
else
  log "    no existing acceptance source — creating one"
  curl_json -X POST "${PC_URL}/v1/sources/with-version" \
    -H "Content-Type: application/json" \
    -d "${CREATE_PAYLOAD}" | tee "${RUN_DIR}/create.json" >/dev/null
  SOURCE_ID="$(jq -r '.source.source_id // .source.id // .source_id // empty' < "${RUN_DIR}/create.json")"
  SOURCE_VERSION_ID="$(jq -r '.source_version.source_version_id // .source_version.id // .source_version_id // empty' < "${RUN_DIR}/create.json")"
fi
if [[ -z "${SOURCE_ID}" || -z "${SOURCE_VERSION_ID}" ]]; then
  echo "error: source creation did not return source/source_version ids" >&2
  cat "${RUN_DIR}/create.json" >&2
  exit 1
fi
log "    source_id=${SOURCE_ID} source_version_id=${SOURCE_VERSION_ID}"

# ── 3. Readiness ───────────────────────────────────────────────────────────
log "==> Checking readiness"
curl_json "${PC_URL}/v1/runs/readiness?source_id=${SOURCE_ID}&source_version_id=${SOURCE_VERSION_ID}&mode=${RUN_MODE}" \
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
RUN_PAYLOAD="$(jq -n --arg source_id "${SOURCE_ID}" --arg source_version_id "${SOURCE_VERSION_ID}" --arg run_mode "${RUN_MODE}" --argjson max_resources "${MAX_RESOURCES}" '{
  source_id: $source_id,
  source_version_id: $source_version_id,
  mode: $run_mode,
  scope: { kind: "discovered_subset", max_resources: $max_resources }
}')"

log "==> Launching ${RUN_MODE} run"
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
# Computed here, not with the other content gates below, because the DI wait now
# needs it: the loop must know how many documents it is waiting FOR.
captured_count="$(jq -r '.captured_resources_count // (.data | length) // 0' < "${RUN_DIR}/preview-summary.json")"
log "==> Waiting for DI canonical_ready + document.processed (${captured_count} captured)"
canonical_ready_count=0
processed_count=0
for i in $(seq 1 "${DI_MAX_POLLS}"); do
  curl_json "${PC_URL}/v1/runs/${RUN_ID}/processing-status" | tee "${RUN_DIR}/processing-status.json" >/dev/null
  curl_json "${PC_URL}/v1/runs/${RUN_ID}/document-lifecycle" | tee "${RUN_DIR}/document-lifecycle.json" >/dev/null
  canonical_ready_count="$(jq -r '[.data[]? | select(.status=="canonical_ready")] | length' < "${RUN_DIR}/processing-status.json")"
  processed_count="$(jq -r '[.data[]? | select(.event_type=="document.processed")] | length' < "${RUN_DIR}/document-lifecycle.json")"
  log "  di poll ${i}/${DI_MAX_POLLS}: canonical_ready=${canonical_ready_count}/${captured_count} processed=${processed_count}"
  # Wait for EVERY captured document, not the first one. This used to break on
  # `canonical_ready > 0`, which made the harness sample the pipeline mid-flight:
  # a 4-document run was reported as 4 captured / 3 canonical_ready and the
  # missing one looked like a silent loss when it was merely still processing.
  # Worse, the verdict below then declared `pass` over the partial result.
  if [[ "${canonical_ready_count}" -ge "${captured_count}" && "${processed_count}" -gt 0 ]]; then
    break
  fi
  sleep "${DI_POLL_INTERVAL}"
done

# NOTHING arriving is a different failure from SOME arriving, and it has one
# overwhelmingly likely cause. platform-control defaults to the `noop` publisher
# and the `local` artifact store, so it captures the documents, reports the run
# `completed`, and publishes no event at all — DI then sits idle and this loop
# burns its whole budget waiting for a handoff that was never made.
#
# Every `docker compose up platform-control-api` re-applies those defaults unless
# the env vars are passed again, so this survives a correct initial bring-up and
# reappears after any rebuild. It cost three debugging cycles before being named
# here; the diagnostic is cheaper than the fourth.
di_diag_artifacts="$(jq -r '.total // (.data | length) // 0' < "${RUN_DIR}/raw-artifacts.json")"
if [[ "${canonical_ready_count}" -eq 0 && "${di_diag_artifacts}" -gt 0 ]]; then
  log "    NOTE: nothing reached DI at all — not a slow pipeline."
  log "          platform-control captured ${captured_count} document(s) and published no event."
  log "          Check the publisher backend; the defaults are noop/local:"
  log "            docker exec <platform-control-api> sh -c 'echo \$PLATFORM_CONTROL_EVENT_PUBLISHER_BACKEND'"
  log "          Expected 'nats'. Re-up with BOTH env vars set (see this file's header)."
fi

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
#
# `expected_language()` returns "" for any template without a `_de`/`_fr`/`_it`
# suffix, and this gate then defaults to `indexed_language_ok=1` — a pass it never
# earned. `indexed_language_checked` records whether the facet was actually read
# (#744); the verdict logic is unchanged.
EXPECTED_LANG="$(expected_language)"
indexed_language_ok=1
indexed_language_checked=0
indexed_language_observed=""
if [[ -z "${EXPECTED_LANG}" ]]; then
  log "==> Indexed-language gate: SKIPPED (not applicable) — template ${TEMPLATE_ID} has no language suffix"
else
  processed_document_ids="$(jq -r '[.data[]? | select(.event_type=="document.processed") | .document_id] | unique | join(" ")' < "${RUN_DIR}/document-lifecycle.json")"
  if [[ -z "${processed_document_ids}" ]]; then
    indexed_language_ok=0
  else
    indexed_language_checked=1
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

# ── 8c. Assert the INDEXED title, not just the captured one (#772) ─────────
# `title_ok` below reads `captured-resources.json` — the provider's title at
# acquisition. Anything the pipeline does to a title afterwards is invisible to it,
# and #771 is what that cost: Fedlex leaked a source filename into `<title>`, the
# pipeline ranked it above the correct captured title, and the Tierschutzgesetz was
# indexed under `fedlex-data-admin-ch-eli-cc-2008-414-20230901-de-docx`. The run
# reported `title_ok=2` and passed, while the law was unfindable by its own name.
#
# The language gate above already reads back from legal-search. Title now does too:
# a title is what every reader searches by, so an unasserted one is not a lesser
# defect than a wrong language facet.
TITLE_REGEX="$(expected_title_regex)"
title_checked="$(title_gate_checked)"
indexed_title_ok=0
indexed_title_checked=0
indexed_title_observed=""
indexed_title_expected_count=0
if [[ "${title_checked}" -eq 0 ]]; then
  log "==> Indexed-title gate: SKIPPED — no title regex to assert for template ${TEMPLATE_ID}"
else
  processed_document_ids="$(jq -r '[.data[]? | select(.event_type=="document.processed") | .document_id] | unique | join(" ")' < "${RUN_DIR}/document-lifecycle.json")"
  if [[ -z "${processed_document_ids}" ]]; then
    log "==> Indexed-title gate: no processed documents to assert"
  else
    indexed_title_checked=1
    read -ra title_doc_ids <<< "${processed_document_ids}"
    indexed_title_expected_count="${#title_doc_ids[@]}"
    log "==> Asserting indexed title matches /${TITLE_REGEX}/ for: ${processed_document_ids}"
    for doc_id in "${title_doc_ids[@]}"; do
      observed_title="missing"
      for i in $(seq 1 "${SEARCH_MAX_POLLS}"); do
        if curl_json "${LS_URL}/v1/documents/${doc_id}" > "${RUN_DIR}/ls-document-${doc_id}.json" 2>/dev/null; then
          observed_title="$(jq -r '.title // "missing"' < "${RUN_DIR}/ls-document-${doc_id}.json")"
          break
        fi
        log "  title poll ${i}/${SEARCH_MAX_POLLS}: ${doc_id} not projected yet"
        sleep "${SEARCH_POLL_INTERVAL}"
      done
      indexed_title_observed="${indexed_title_observed}${indexed_title_observed:+,}${doc_id}=${observed_title}"
      if printf '%s' "${observed_title}" | grep -Eq "${TITLE_REGEX}"; then
        indexed_title_ok=$((indexed_title_ok + 1))
      else
        log "  title mismatch: ${doc_id} expected=/${TITLE_REGEX}/ observed=${observed_title}"
      fi
    done
  fi
fi

# ── 9. Content gates (reused from ch-fedlex-fast-loop.sh) ───────────────────
content_type_count="$(jq -r --arg expect_content_type "${EXPECT_CONTENT_TYPE}" '[.content_type_breakdown[]? | select(.content_type==$expect_content_type) | .count] | add // 0' < "${RUN_DIR}/preview-summary.json")"
raw_artifact_count="$(jq -r '.total // (.data | length) // 0' < "${RUN_DIR}/raw-artifacts.json")"
title_ok="$(jq -r --arg title_regex "${TITLE_REGEX}" '[.data[]? | select((.title // "") | test($title_regex))] | length' < "${RUN_DIR}/captured-resources.json")"
accepted_count="$(jq -r '[.data[]? | select(.status=="accepted")] | length' < "${RUN_DIR}/processing-status.json")"
processing_count="$(jq -r '[.data[]? | select(.status=="processing")] | length' < "${RUN_DIR}/processing-status.json")"

# ── 9b. Skipped-gate ledger (#744) ─────────────────────────────────────────
# A gate that self-skipped is reported as skipped, never folded into the pass count.
# `skipped_gates` being empty is what an operator needs before flipping
# `enabled: true` under ADR-0030: proof every gate actually ran.
skipped_gates=()
[[ "${title_checked}" -eq 1 ]] || skipped_gates+=("title_ok")
[[ "${indexed_title_checked}" -eq 1 ]] || skipped_gates+=("indexed_title_ok")
# checked=0 with ok=1 is a genuine skip; checked=0 with ok=0 is a real failure the
# verdict already catches.
if [[ "${indexed_language_checked}" -eq 0 && "${indexed_language_ok}" -eq 1 ]]; then
  skipped_gates+=("indexed_language_ok")
fi
skipped_gates_json="$(jq -nc '$ARGS.positional' --args "${skipped_gates[@]+"${skipped_gates[@]}"}")"

if [[ "${#skipped_gates[@]}" -gt 0 ]]; then
  log "==> Gates NOT evaluated for template ${TEMPLATE_ID} — reported as skipped, not as passes (#744):"
  for skipped_gate in "${skipped_gates[@]}"; do
    log "    - ${skipped_gate}: skipped (not applicable)"
  done
fi

# ── 10. Verdict ────────────────────────────────────────────────────────────
verdict="pass"
if [[ "${content_type_count}" -lt 1 || "${captured_count}" -lt 1 || "${raw_artifact_count}" -lt 1 ]]; then
  verdict="provider_failed"
elif [[ "${accepted_count}" -lt 1 || "${canonical_ready_count}" -lt 1 || "${processed_count}" -lt 1 ]]; then
  verdict="downstream_failed"
elif [[ "${canonical_ready_count}" -lt "${captured_count}" ]]; then
  # Every captured document must reach canonical, not just one. Nothing compared
  # these two counts, so a run that captured 4 and canonicalised 1 reported
  # `pass` — and this bundle is the evidence an operator flips `enabled: true`
  # on (ADR-0030). Evidence over a pipeline that dropped three quarters of the
  # corpus is not evidence. #772 already established the principle for titles
  # ("a partial failure is a failure"); it was never applied to document count.
  verdict="downstream_incomplete"
elif [[ ! "${search_hits}" =~ ^[0-9]+$ || "${search_hits}" -lt 1 ]]; then
  # The whole point of Stream H: DI output must reach legal-search via the
  # projection-bridge and be searchable.
  verdict="search_failed"
elif [[ "${title_ok}" -lt 1 || "${indexed_language_ok}" -lt 1 ]]; then
  verdict="pipeline_pass_content_suspect"
elif [[ "${indexed_title_checked}" -eq 1 && "${indexed_title_ok}" -lt "${indexed_title_expected_count}" ]]; then
  # EVERY processed document must carry a matching title, not just one of them
  # (#772). `title_ok` is a count tested against 1, so a run where 1 of 20 titles
  # survived reported `pass`. A partial failure is a failure.
  verdict="pipeline_pass_content_suspect"
fi

SUMMARY_JSON="$(jq -n \
  --arg template_id "${TEMPLATE_ID}" \
  --arg overlay_id "${OVERLAY_ID}" \
  --arg run_mode "${RUN_MODE}" \
  --arg jurisdiction_id "${JURISDICTION_ID}" \
  --arg authority_id "${AUTHORITY_ID}" \
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
  --arg expect_content_type "${EXPECT_CONTENT_TYPE}" \
  --argjson content_type_match_count "${content_type_count}" \
  --argjson accepted_count "${accepted_count}" \
  --argjson processing_count "${processing_count}" \
  --argjson canonical_ready_count "${canonical_ready_count}" \
  --argjson processed_count "${processed_count}" \
  --argjson title_ok "${title_ok}" \
  --argjson title_checked "${title_checked}" \
  --argjson indexed_title_ok "${indexed_title_ok}" \
  --argjson indexed_title_checked "${indexed_title_checked}" \
  --argjson indexed_title_expected_count "${indexed_title_expected_count}" \
  --arg indexed_title_observed "${indexed_title_observed}" \
  --argjson skipped_gates "${skipped_gates_json}" \
  --argjson search_hits "${search_hits}" \
  --argjson indexed_language_ok "${indexed_language_ok}" \
  --argjson indexed_language_checked "${indexed_language_checked}" \
  --arg indexed_language_expected "${EXPECTED_LANG}" \
  --arg indexed_language_observed "${indexed_language_observed}" \
  '{
    environment: "compose-local",
    template_id: $template_id,
    overlay_id: $overlay_id,
    run_mode: $run_mode,
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
      expect_content_type: $expect_content_type,
      content_type_match_count: $content_type_match_count,
      accepted_count: $accepted_count,
      processing_count: $processing_count,
      canonical_ready_count: $canonical_ready_count,
      processed_count: $processed_count,
      title_ok: $title_ok,
      title_checked: $title_checked,
      indexed_title_ok: $indexed_title_ok,
      indexed_title_checked: $indexed_title_checked,
      indexed_title_expected_count: $indexed_title_expected_count,
      indexed_title_observed: $indexed_title_observed,
      skipped_gates: $skipped_gates,
      search_hits: $search_hits,
      indexed_language_expected: $indexed_language_expected,
      indexed_language_observed: $indexed_language_observed,
      indexed_language_checked: $indexed_language_checked,
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
