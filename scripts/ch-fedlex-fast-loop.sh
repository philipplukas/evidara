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
# How long to wait for legal-search to serve back each processed document. The
# default of 12 x 5s was set for a small HTML corpus and is too short for one that
# takes an extraction step: a 7-document PDF run on 2026-09-17 was still
# unqueryable at 60s and fully queryable shortly after, which reported the
# indexed-language and indexed-title gates as NOT EVALUATED and made an otherwise
# clean run unusable as acceptance evidence. Raise it for a slow corpus rather
# than accepting a hole in the gates (#744: not_evaluated is a hole, not an
# exclusion).
READBACK_POLLS=12
# Floor for the largest canonical body, in characters. 10 KB suits a federal or
# cantonal act; it is wrong for a municipal one. Measured 2026-09-17: Stadt
# Zürich's "Vollzugsvorschriften zum Hundegesetz" — the exact ordinance ADR-0033's
# dog question needs, captured correctly, indexed correctly, `art_density=8`,
# title and language both asserted — is 3,080 characters and failed this gate
# alone.
#
# A floor calibrated on one corpus withholds real data on the next one, which
# AGENTS.md already records happening with a marker floor of 3. So it is a
# corpus-shape parameter like --expect-content-type, not a constant. The DEFAULT
# is unchanged, so every existing driver and the nightly canaries keep the floor
# they had.
#
# Lowering it does not make the run green by itself: `art_density_ok` is the
# primary legal-text signal and still has to pass, and it is the one that catches
# a navigation shell captured instead of the law (#631).
MIN_CONTENT_LENGTH=10240
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
# Explicit corpus expectations, empty by default (#744). Empty => fall back to the
# template-id derivation below, so the nightly Fedlex canary is bit-for-bit
# unchanged. Set => the gate RUNS and reports `*_checked=1`, which is the whole
# point: without these two flags a non-Fedlex template could not make the title or
# language gate run at all, and a run that asserts neither is not evidence about
# either (the `excluded` vs `not_evaluated` split in the acceptance verdict).
EXPECT_TITLE=""
EXPECT_LANGUAGE=""
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
  --expect-title <regex>         Title the indexed document must match. Unset => derived
                                 from the template id, and for an unknown template the
                                 gate does NOT run (reported title_checked=0).
  --expect-language <code>       Language the indexed document must carry. Unset => derived
                                 from the template's _de/_fr/_it suffix; a template with
                                 no suffix leaves the gate excluded.
  --corpus-slug <slug>           Slug used in the --copy-evidence filename (default: ch-fedlex)
  --corpus-label <label>         Human corpus name in the evidence markdown (default: CH Fedlex)
  --mode <preview|acceptance|production>
                                 Run mode (default: preview). Use `acceptance` for a
                                 provider whose readiness is `awaiting_evidence` —
                                 `preview` is refused by the two-key lock there (#743).
  --max-resources <n>            Preview scope max_resources (default: 25)
  --max-polls <n>                Maximum run polls (default: 60)
  --min-content-length <n>       Floor for the largest canonical body, in characters
                                 (default: 10240). A municipal ordinance is legitimately
                                 far shorter than a federal act; art_density_ok stays the
                                 primary legal-text signal either way.
  --readback-polls <n>           Polls (x5s) waiting for legal-search to serve each
                                 processed document back (default: 12). A corpus with an
                                 extraction step needs more, or the indexed-language and
                                 indexed-title gates report NOT EVALUATED.
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
    --expect-title)
      EXPECT_TITLE="${2:?missing value for --expect-title}"
      shift 2
      ;;
    --expect-language)
      EXPECT_LANGUAGE="${2:?missing value for --expect-language}"
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
      # An argv value is readable by any local user for the life of the process:
      # `ps -eo cmd` and /proc/<pid>/cmdline both show it, and so does any tool
      # that snapshots the process table. The key then survives in shell history
      # and in the scrollback of whatever ran this. EVIDARA_PLATFORM_CONTROL_API_KEY
      # (read at :51) has neither problem, so warn rather than accept silently.
      echo "warning: --api-key puts the key in this process's argv, where any local" >&2
      echo "         user can read it via \`ps\` or /proc. Prefer:" >&2
      echo "           export EVIDARA_PLATFORM_CONTROL_API_KEY=...  # then omit --api-key" >&2
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
    --readback-polls)
      READBACK_POLLS="${2:?missing value for --readback-polls}"
      shift 2
      ;;
    --min-content-length)
      MIN_CONTENT_LENGTH="${2:?missing value for --min-content-length}"
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

# Auth for the read-back gates (indexed language, indexed title). Two shapes,
# because there are two runtimes:
#
#   Cloud Run     a minted identity token   (EVIDARA_LEGAL_SEARCH_TOKEN)
#   self-hosted   an X-API-Key              (EVIDARA_LEGAL_SEARCH_API_KEY)
#
# The comment here used to read "legal-search is public-by-default in self-hosted
# mode", and the X-API-Key branch did not exist. That stopped being true when
# legal-search started failing closed: every request without a key answers 401,
# `curl -fsS` exits non-zero, the read-back loop treats it as "projection not
# queryable yet" and burns its whole poll budget. The gates then report
# NOT EVALUATED — a hole, not an exclusion (#744) — so every self-hosted bundle
# produced since then disqualifies itself as acceptance evidence, for a reason
# that has nothing to do with the corpus. Measured 2026-09-17: a run whose eight
# documents all returned 200 to a hand-rolled curl polled 60 times and wrote a
# zero-byte read-back file each time.
LS_AUTH_HEADER=()
if [[ -n "${EVIDARA_LEGAL_SEARCH_TOKEN:-}" ]]; then
  LS_AUTH_HEADER=(-H "Authorization: Bearer ${EVIDARA_LEGAL_SEARCH_TOKEN}")
elif [[ -n "${EVIDARA_LEGAL_SEARCH_API_KEY:-}" ]]; then
  LS_AUTH_HEADER=(-H "X-API-Key: ${EVIDARA_LEGAL_SEARCH_API_KEY}")
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

expected_title_regex() {
  if [[ -n "${EXPECT_TITLE}" ]]; then
    printf '%s' "${EXPECT_TITLE}"
    return
  fi
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
  if [[ -n "${EXPECT_TITLE}" ]]; then
    printf '%s' '1'
    return
  fi
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

# Names the corpus actually being driven, not the script. This runs non-Fedlex
# corpora too (scripts/ch-lexfind-fast-loop.sh delegates here), and a banner that
# says "CH Fedlex" over a LexFind run is a small lie in the one place an operator
# looks to confirm they launched what they meant to.
log "==> ${CORPUS_LABEL} fast loop"
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
curl_json "${PC_URL}/v1/runs/readiness?source_id=${SOURCE_ID}&source_version_id=${SOURCE_VERSION_ID}&mode=${RUN_MODE}" | tee "${RUN_DIR}/readiness.json" >/dev/null
READY="$(jq -r '.ready' < "${RUN_DIR}/readiness.json")"
if [[ "${READY}" != "true" ]]; then
  echo "error: readiness returned ready=${READY}" >&2
  cat "${RUN_DIR}/readiness.json" >&2
  exit 1
fi

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
title_checked="$(title_gate_checked)"
content_type_count="$(jq -r --arg expect_content_type "${EXPECT_CONTENT_TYPE}" '[.content_type_breakdown[]? | select(.content_type==$expect_content_type) | .count] | add // 0' < "${RUN_DIR}/preview-summary.json")"
raw_artifact_count="$(jq -r '.total // (.data | length) // 0' < "${RUN_DIR}/raw-artifacts.json")"
title_ok="$(jq -r --arg title_regex "${TITLE_REGEX}" '[.data[]? | select((.title // "") | test($title_regex))] | length' < "${RUN_DIR}/captured-resources.json")"
url_pattern_ok="$(jq -r --arg url_pattern "${URL_PATTERN}" '[.data[]? | select((.final_url // "") | test($url_pattern))] | length' < "${RUN_DIR}/captured-resources.json")"
# The FIRST article, under any of the drafting conventions this corpus set uses.
# It is the only gate that distinguishes a complete document from a fragment
# starting mid-text: art_density_ok passes on a fragment just as well.
#
#   Art. 1                Fedlex, and most modern Swiss and Austrian acts
#   § 1                   BS/BL/AG/SO/LU/SH/TG/ZG, and German Land law
#   Art. I                19th-century Swiss treaties and older acts
#
# The Roman branch needs the negative lookahead to stay a FIRST-article check:
# it matches "Art. I3" (article I, footnote marker 3) and rejects "Art. II4".
# Without it, any Roman-numbered article would satisfy the gate.
#
# Measured 2026-09-17 on SR 0.142.115.141, the 1875 Niederlassungsvertrag with
# Liechtenstein, reached by fedlex_sparql_sr_full_de's enumeration: a complete
# document — preamble, Art. I through Art. VI, signatures "So geschehen zu Wien,
# am 6. Juli 1874" — whose only ARABIC "Art. 3" occurrences are cross-references
# to other agreements. It failed this gate and took the run's verdict with it.
#
# This is a whitelist of conventions, and it should be read as one. French
# ("Article premier") and Italian ("Art. 1-bis") are not covered yet and will
# surface the same way: a correct corpus reported as suspect.
# Each branch needs its own negative lookahead, or the gate passes on a fragment
# that begins at a LATER article: bare `Art\. 1` matches "Art. 12", which is how
# the original pattern read. `(?![0-9])` keeps "Art. 1a" — a real article — while
# rejecting "Art. 12" and "Art. 19".
# SINGLE backslashes. The old pattern lived inside a jq string literal, where
# `\\.` unescapes to `\.`; passed through `--arg` jq takes the value verbatim, so
# `\\.` would mean a literal backslash followed by any character and the gate would
# match nothing. Verified against production, not just in a unit test — the first
# draft of that test re-applied the unescaping itself and passed while the run
# failed.
ART1_PATTERN='Art\. 1(?![0-9])|§ ?1(?![0-9])|Art\. I(?![IVXLC])'
art1_ok="$(jq -r --arg art1 "${ART1_PATTERN}" '[.data[]? | select(
  ((.artifact_metadata.inline_body // "") | test($art1))
  or ((.artifact_metadata.body // "") | test($art1))
  or ((.artifact_metadata.provider_metadata.inline_body // "") | test($art1))
  or ((.artifact_metadata.provider_metadata.body // "") | test($art1))
)] | length' < "${RUN_DIR}/raw-artifacts.json")"
accepted_count="$(jq -r '[.data[]? | select(.status=="accepted")] | length' < "${RUN_DIR}/processing-status.json")"
processing_count="$(jq -r '[.data[]? | select(.status=="processing")] | length' < "${RUN_DIR}/processing-status.json")"
canonical_ready_count="$(jq -r '[.data[]? | select(.status=="canonical_ready")] | length' < "${RUN_DIR}/processing-status.json")"
processed_count="$(jq -r '[.data[]? | select(.event_type=="document.processed")] | length' < "${RUN_DIR}/document-lifecycle.json")"

# --- Content quality gates ---

# Legal-text density: at least 3 article markers across the corpus.
#
# BOTH "Art." AND "§", because the marker depends on the drafting tradition, not
# on whether the text is law. Counting only "Art." reported a genuine Basel-Stadt
# statute corpus as having no legal text at all — measured 2026-09-17 over four
# indexed BS documents:
#
#     "Art." = 1        "§" = 126
#     (the 24,225-character Hundeverordnung alone: 0 and 87)
#
# BS, BL, AG, SO, LU, SH, TG and ZG all draft in §, and German Land law uses it
# almost exclusively — so `bundesland_http_bayern` would have failed the same way.
# The gate was calibrated on Fedlex, which uses "Art.", and silently withheld
# every § corpus.
#
# This widens what counts as law; it does not weaken the gate. "§" is an article
# marker in exactly the same sense, and the floor of 3 is unchanged.
art_density_count="$(jq -r '[.data[]? |
  ((.artifact_metadata.inline_body // "") + (.artifact_metadata.body // "") +
   (.artifact_metadata.provider_metadata.inline_body // "") + (.artifact_metadata.provider_metadata.body // ""))
] | map([ match("Art\\.|§"; "g") ] | length) | add // 0' < "${RUN_DIR}/raw-artifacts.json")"
art_density_ok=$(( art_density_count >= 3 ? 1 : 0 ))

# Minimum content length: at least 10 KB (10240 bytes) in the largest artifact body
body_max_length="$(jq -r '[.data[]? |
  [(.artifact_metadata.inline_body // "" | length),
   (.artifact_metadata.body // "" | length),
   (.artifact_metadata.provider_metadata.inline_body // "" | length),
   (.artifact_metadata.provider_metadata.body // "" | length)] | max
] | max // 0' < "${RUN_DIR}/raw-artifacts.json")"
min_content_length_ok=$(( body_max_length >= MIN_CONTENT_LENGTH ? 1 : 0 ))

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
# Why the read-back block did not run, when it did not. The indexed-title gate rides on
# this block, so it inherits the reason: a template that declares no language never
# reaches the read-back at all, and its title gate is then NOT EVALUATED — asked for and
# missed — rather than excluded. Conflating the two is what let a run with an
# unreachable legal-search render as "not applicable to this template" (#744).
readback_skip_reason=""

if [[ -z "${expected_lang}" ]]; then
  # Skipped, not passed. `indexed_language_checked` used to be set to 1 here, which
  # reported a facet assertion that never happened — the same green-because-it-never-ran
  # defect as #605/#675/#713. Keep `_ok=1` so the skip does not newly block the verdict
  # (#744 changes visibility only); `_checked=0` is what tells the reader it did not run.
  log "==> Indexed-language gate: EXCLUDED (not applicable) — template ${TEMPLATE_ID} has no language suffix"
  indexed_language_checked=0
  indexed_language_ok=1
  readback_skip_reason="no_expected_language_declared"
elif [[ -z "${LS_URL}" ]]; then
  log "==> Indexed-language gate: NOT EVALUATED — no legal-search URL."
  log "    Pass --ls-url (self-hosted: kubectl -n evidara port-forward svc/legal-search-api 3102:3000)"
  log "    so the run can prove the search facet, not just the raw body."
  readback_skip_reason="no_legal_search_url"
elif [[ -z "${processed_document_ids}" ]]; then
  log "==> Indexed-language gate: NOT EVALUATED — no document.processed events to check"
  readback_skip_reason="no_processed_documents"
else
  log "==> Asserting indexed language=${expected_lang} for: ${processed_document_ids}"
  read -ra doc_ids <<< "${processed_document_ids}"
  for attempt in $(seq 1 "${READBACK_POLLS}"); do
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
    log "  indexed-language poll ${attempt}/${READBACK_POLLS}: projection not queryable yet"
    sleep 5
  done

  if [[ "${indexed_language_checked}" -ne 1 ]]; then
    log "  indexed-language gate could not read the projection from legal-search"
    readback_skip_reason="projection_not_queryable"
  fi
fi

# --- Content gates, re-measured against the CANONICAL text (#1014) ---
#
# The three gates above read the RAW artifact. For an HTML corpus that is the
# document; for a binary one it is nothing at all. Measured 2026-09-17 on
# `lexfind_api_zh_full`: all 8 raw PDFs carried `inline_body` and `body` of
# length 0, so art_density=0, body_max_length=0 and min_content_length_ok=0 for a
# run that processed 8/8/8 and indexed 152,853 characters per document. The
# verdict was `pipeline_pass_content_suspect` for a corpus that was entirely fine.
#
# Weakening the thresholds would have made every corpus pass by construction.
# Marking the gates `excluded` would have made them abstain on the format half our
# providers return. So they are re-measured where the text actually is: the
# canonical document the pipeline produced and legal-search serves, which is also
# what a user reads. That asserts MORE than the raw body did, not less — it covers
# extraction as well as capture.
#
# The readback loop above has already written ls-document-*.json for every
# processed document, so this costs no extra requests.
#
# The raw-artifact numbers are kept and reported alongside, because a corpus whose
# raw body IS the document (fedlex HTML) should not silently lose that signal.
content_gate_source="raw_artifact"
canonical_bodies=("${RUN_DIR}"/ls-document-*.json)
if [[ -e "${canonical_bodies[0]}" ]]; then
  canonical_max_length="$(jq -rs '[.[] | (.content // "") | length] | max // 0' "${canonical_bodies[@]}")"
  # Only switch when the canonical text is actually there. A projection that
  # returned 200 with an empty body must not silently replace a raw measurement
  # with a zero — that would turn this fix into the defect it is fixing.
  if [[ "${canonical_max_length}" -gt 0 ]]; then
    content_gate_source="canonical"
    raw_art_density_count="${art_density_count}"
    raw_body_max_length="${body_max_length}"
    # Same marker set as the raw path above: "Art." OR "§".
    art_density_count="$(jq -rs '[.[] | (.content // "") | [ match("Art\\.|§"; "g") ] | length] | add // 0' "${canonical_bodies[@]}")"
    art_density_ok=$(( art_density_count >= 3 ? 1 : 0 ))
    body_max_length="${canonical_max_length}"
    min_content_length_ok=$(( body_max_length >= MIN_CONTENT_LENGTH ? 1 : 0 ))
    # Same convention set as the raw path above (ART1_PATTERN).
    art1_ok="$(jq -rs --arg art1 "${ART1_PATTERN}" '[.[] | select((.content // "") | test($art1))] | length' "${canonical_bodies[@]}")"
    log "==> Content gates re-measured against the canonical text (${content_gate_source})"
    log "    raw artifact: art_density=${raw_art_density_count} body_max_length=${raw_body_max_length}"
    log "    canonical:    art_density=${art_density_count} body_max_length=${body_max_length}"
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

# --- Gate-coverage ledger (#744; split into excluded/not-evaluated) ---
#
# A gate that did not run must be reported as not-run, never folded into the pass count.
# WHY it did not run is what decides whether this bundle is still acceptance evidence:
#
#   excluded      — nobody asked for it (this template declares no title pattern, no
#                   language). Unverified, but not a hole: still citable under ADR-0030.
#   not_evaluated — it was asked for and could not run (legal-search unreachable, the
#                   projection never queryable, nothing processed to assert over). A hole
#                   in the evidence; the CLI refuses the `enabled: true` flip on it
#                   (`tools/evidara-cli/src/evidara_cli/gate_coverage.py`).
#
# Names follow Soda Core v4's `CheckOutcome.EXCLUDED` / `NOT_EVALUATED`, which draws the
# same line and escalates only the second.
gate_ledger_reset
[[ "${title_checked}" -eq 1 ]] || gate_excluded "title_ok" "no_expected_title_declared"
[[ "${body_lang_hint_checked}" -eq 1 ]] || gate_excluded "body_lang_hint_ok" "not_a_german_template"
# indexed_language_checked=0 with _ok=1 is a gate nobody asked for; with _ok=0 it is a
# fail-closed "could not evaluate", which the verdict already catches — so it is a
# failure, not a coverage entry.
if [[ "${indexed_language_checked}" -eq 0 && "${indexed_language_ok}" -eq 1 ]]; then
  gate_excluded "indexed_language_ok" "no_expected_language_declared"
fi
if [[ "${indexed_title_checked}" -ne 1 ]]; then
  if [[ "${title_checked}" -ne 1 ]]; then
    gate_excluded "indexed_title_ok" "no_expected_title_declared"
  else
    # A title regex WAS declared and the gate still did not run. That is a hole, and
    # `readback_skip_reason` names which one. It is never empty here: the read-back
    # block sets it on every path that leaves `indexed_title_checked` at 0.
    gate_not_evaluated "indexed_title_ok" "${readback_skip_reason:-reason_not_recorded}"
  fi
fi
gate_coverage_json="$(gate_ledger_json)"
skipped_gates_json="$(gate_ledger_names_json)"
excluded_gates_json="$(gate_ledger_names_json excluded)"
not_evaluated_gates_json="$(gate_ledger_names_json not_evaluated)"

if [[ "${#GATE_LEDGER[@]}" -gt 0 ]]; then
  log "==> Gate coverage for template ${TEMPLATE_ID} — not folded into the pass count (#744):"
  gate_ledger_log
fi

verdict="pass"
if [[ "${content_type_count}" -lt 1 || "${captured_count}" -lt 1 || "${raw_artifact_count}" -lt 1 ]]; then
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
  --arg content_gate_source "${content_gate_source}" \
  --argjson body_max_length "${body_max_length}" \
  --argjson min_content_length_ok "${min_content_length_ok}" \
  --argjson min_content_length_floor "${MIN_CONTENT_LENGTH}" \
  --argjson lang_agreement_ok "${lang_agreement_ok}" \
  --argjson body_lang_hint_ok "${body_lang_hint_ok}" \
  --argjson body_lang_hint_checked "${body_lang_hint_checked}" \
  --argjson skipped_gates "${skipped_gates_json}" \
  --argjson gate_coverage "${gate_coverage_json}" \
  --argjson excluded_gates "${excluded_gates_json}" \
  --argjson not_evaluated_gates "${not_evaluated_gates_json}" \
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
      # Which text the three content gates above were measured against (#1014):
      # `canonical` is the document the pipeline produced and legal-search serves;
      # `raw_artifact` is the bytes as captured. A binary corpus has no raw text at
      # all, so a bundle reporting `raw_artifact` with a PDF content type is
      # reporting gates that could not have found anything.
      content_gate_source: $content_gate_source,
      body_max_length: $body_max_length,
      min_content_length_ok: $min_content_length_ok,
      # The floor this run was measured against. A bundle that passed with a
      # lowered floor must say so, or a reader cannot tell a short municipal
      # ordinance from a weakened gate.
      min_content_length_floor: $min_content_length_floor,
      lang_agreement_ok: $lang_agreement_ok,
      body_lang_hint_ok: $body_lang_hint_ok,
      body_lang_hint_checked: $body_lang_hint_checked,
      # Retained as the union of the two lists below so every existing reader keeps
      # working; `gate_coverage` is what says which kind each one is.
      skipped_gates: $skipped_gates,
      gate_coverage: $gate_coverage,
      excluded_gates: $excluded_gates,
      not_evaluated_gates: $not_evaluated_gates,
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
