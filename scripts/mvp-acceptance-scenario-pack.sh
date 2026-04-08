#!/usr/bin/env bash
# MVP acceptance scenario pack — HTTP evidence for dev/staging.
# See docs/runbooks/mvp-acceptance-scenario-pack.md
#
# Usage:
#   ./scripts/mvp-acceptance-scenario-pack.sh dev
#   ./scripts/mvp-acceptance-scenario-pack.sh staging
#   ./scripts/mvp-acceptance-scenario-pack.sh dev --json
#
# Optional overrides (full base URLs, no trailing slash):
#   PC_API_URL, LS_API_URL, LS_FRONTEND_URL, ADMIN_FRONTEND_URL
#
# Authentication: uses gcloud identity token with per-host audience when available.

set -euo pipefail

usage() {
  cat >&2 <<EOF
Usage: $0 dev|staging [--json]
EOF
}

if [[ $# -lt 1 ]]; then
  usage
  exit 1
fi

ENV="$1"
shift
JSON_ONLY=0

while [[ $# -gt 0 ]]; do
  case "$1" in
    --json)
      JSON_ONLY=1
      shift
      ;;
    *)
      echo "Unknown argument: $1" >&2
      usage
      exit 1
      ;;
  esac
done

case "${ENV}" in
  dev)
    PC_API="${PC_API_URL:-https://platform-control-api-dev-kxc5agexna-oa.a.run.app}"
    LS_API="${LS_API_URL:-https://legal-search-api-dev-kxc5agexna-oa.a.run.app}"
    LS_UI="${LS_FRONTEND_URL:-https://legal-search-frontend-dev-kxc5agexna-oa.a.run.app}"
    ADMIN_UI="${ADMIN_FRONTEND_URL:-https://platform-control-admin-dev-kxc5agexna-oa.a.run.app}"
    ;;
  staging)
    PC_API="${PC_API_URL:-https://platform-control-api-staging-kxc5agexna-oa.a.run.app}"
    LS_API="${LS_API_URL:-https://legal-search-api-staging-kxc5agexna-oa.a.run.app}"
    LS_UI="${LS_FRONTEND_URL:-https://legal-search-frontend-staging-kxc5agexna-oa.a.run.app}"
    ADMIN_UI="${ADMIN_FRONTEND_URL:-https://platform-control-admin-staging-kxc5agexna-oa.a.run.app}"
    ;;
  *)
    echo "Unknown env: ${ENV} (use dev or staging)" >&2
    exit 1
    ;;
esac

log() {
  if [[ "${JSON_ONLY}" -eq 0 ]]; then
    echo "$@"
  fi
}

token_for_url() {
  local base="$1"
  if ! command -v gcloud >/dev/null 2>&1; then
    echo ""
    return
  fi
  gcloud auth print-identity-token --audiences="${base}" 2>/dev/null || true
}

http_code() {
  local url="$1"
  local base
  base="$(echo "${url}" | sed -E 's#(https?://[^/]+).*#\1#')"
  local tok
  tok="$(token_for_url "${base}")"
  local auth=()
  if [[ -n "${tok}" ]]; then
    auth=(-H "Authorization: Bearer ${tok}")
  fi
  curl -sS -o /dev/null -w "%{http_code}" --connect-timeout 10 --max-time 60 "${auth[@]}" "${url}" || echo "000"
}

json_body() {
  local url="$1"
  local base
  base="$(echo "${url}" | sed -E 's#(https?://[^/]+).*#\1#')"
  local tok
  tok="$(token_for_url "${base}")"
  local auth=()
  if [[ -n "${tok}" ]]; then
    auth=(-H "Authorization: Bearer ${tok}")
  fi
  curl -sS --connect-timeout 10 --max-time 60 "${auth[@]}" "${url}" || echo ""
}

log "=== MVP acceptance scenario pack: ${ENV} ==="
log "platform-control API: ${PC_API}"
log "legal-search API:     ${LS_API}"
log "legal-search UI:      ${LS_UI}"
log "admin UI:             ${ADMIN_UI}"
log ""

# Scenario 1
log "--- Scenario 1: Platform Control ---"
c1="$(http_code "${PC_API}/health")"
c2="$(http_code "${PC_API}/v1/sources")"
log "GET /health -> ${c1}"
log "GET /v1/sources -> ${c2}"

# Scenario 2
log "--- Scenario 2: Search query pack ---"
declare -a query_rows=()
for q in "art 754" "haftung" "obligationenrecht" "switzerland"; do
  enc="$(printf %s "${q}" | jq -sRr @uri)"
  body="$(json_body "${LS_API}/v1/search?q=${enc}")"
  code="$(http_code "${LS_API}/v1/search?q=${enc}")"
  total="$(echo "${body}" | jq -r '.totalResults // .total_results // "n/a"' 2>/dev/null || echo "n/a")"
  log "q=${q} -> HTTP ${code}, totalResults=${total}"
  query_rows+=("${q}"$'\t'"${code}"$'\t'"${total}")
done

# Scenario 3
log "--- Scenario 3: Document detail ---"
search_json="$(json_body "${LS_API}/v1/search?q=$(printf %s "art 754" | jq -sRr @uri)")"
doc_id="$(echo "${search_json}" | jq -r '.results[0].id // .hits[0].id // empty' 2>/dev/null || true)"
if [[ -z "${doc_id}" || "${doc_id}" == "null" ]]; then
  doc_id="$(echo "${search_json}" | jq -r '.items[0].id // empty' 2>/dev/null || true)"
fi
detail_http_code="n/a"
detail_has_id="no"
detail_has_title="no"
detail_has_subtitle="no"
detail_has_metadata="no"
detail_has_tabs="no"
if [[ -z "${doc_id}" ]]; then
  log "Could not resolve first result id from search payload; skip detail check"
else
  detail="$(json_body "${LS_API}/v1/documents/${doc_id}")"
  detail_http_code="$(http_code "${LS_API}/v1/documents/${doc_id}")"
  detail_has_id="$(echo "${detail}" | jq -e --arg id "${doc_id}" '.id == $id' >/dev/null 2>&1 && echo yes || echo no)"
  detail_has_title="$(echo "${detail}" | jq -e '.title | strings | length > 0' >/dev/null 2>&1 && echo yes || echo no)"
  detail_has_subtitle="$(echo "${detail}" | jq -e '.subtitle | strings | length > 0' >/dev/null 2>&1 && echo yes || echo no)"
  detail_has_metadata="$(echo "${detail}" | jq -e '.metadata | arrays' >/dev/null 2>&1 && echo yes || echo no)"
  detail_has_tabs="$(echo "${detail}" | jq -e '.tabs | arrays' >/dev/null 2>&1 && echo yes || echo no)"
  log "GET /v1/documents/${doc_id} -> HTTP ${detail_http_code} (id:${detail_has_id} title:${detail_has_title} subtitle:${detail_has_subtitle} metadata:${detail_has_metadata} tabs:${detail_has_tabs})"
fi

# Scenario 4
log "--- Scenario 4: Website proxies ---"
ls_ui_root_code="$(http_code "${LS_UI}/")"
ls_ui_search_code="$(http_code "${LS_UI}/v1/search?q=$(printf %s "art%20754")")"
admin_ui_root_code="$(http_code "${ADMIN_UI}/")"
admin_ui_sources_code="$(http_code "${ADMIN_UI}/api/platform-control/v1/sources")"
log "legal-search UI / -> ${ls_ui_root_code}"
log "legal-search UI /v1/search -> ${ls_ui_search_code}"
log "admin UI / -> ${admin_ui_root_code}"
log "admin UI proxied sources -> ${admin_ui_sources_code}"

query_results_json="$(
  printf '%s\n' "${query_rows[@]}" | jq -Rsc '
    split("\n")
    | map(select(length > 0))
    | map(
        split("\t") as $parts
        | {
            query: $parts[0],
            http_code: ($parts[1] | tonumber? // $parts[1]),
            total_results: ($parts[2] | tonumber? // $parts[2])
          }
      )
  '
)"

summary_json="$(
  jq -n \
    --arg environment "${ENV}" \
    --arg pc_api "${PC_API}" \
    --arg ls_api "${LS_API}" \
    --arg ls_ui "${LS_UI}" \
    --arg admin_ui "${ADMIN_UI}" \
    --argjson platform_health "${c1}" \
    --argjson platform_sources "${c2}" \
    --argjson query_results "${query_results_json}" \
    --arg detail_document_id "${doc_id:-}" \
    --arg detail_http_code "${detail_http_code}" \
    --arg detail_has_id "${detail_has_id}" \
    --arg detail_has_title "${detail_has_title}" \
    --arg detail_has_subtitle "${detail_has_subtitle}" \
    --arg detail_has_metadata "${detail_has_metadata}" \
    --arg detail_has_tabs "${detail_has_tabs}" \
    --argjson ls_ui_root "${ls_ui_root_code}" \
    --argjson ls_ui_search "${ls_ui_search_code}" \
    --argjson admin_ui_root "${admin_ui_root_code}" \
    --argjson admin_ui_sources "${admin_ui_sources_code}" \
    '{
      environment: $environment,
      surfaces: {
        platform_control_api: $pc_api,
        legal_search_api: $ls_api,
        legal_search_ui: $ls_ui,
        admin_ui: $admin_ui
      },
      scenario_1: {
        platform_control_health_http_code: $platform_health,
        platform_control_sources_http_code: $platform_sources
      },
      scenario_2: {
        queries: $query_results
      },
      scenario_3: {
        document_id: (if $detail_document_id == "" then null else $detail_document_id end),
        document_http_code: ($detail_http_code | tonumber? // $detail_http_code),
        checks: {
          id_matches_request: ($detail_has_id == "yes"),
          title_present: ($detail_has_title == "yes"),
          subtitle_present: ($detail_has_subtitle == "yes"),
          metadata_is_array: ($detail_has_metadata == "yes"),
          tabs_is_array: ($detail_has_tabs == "yes")
        }
      },
      scenario_4: {
        legal_search_ui_root_http_code: $ls_ui_root,
        legal_search_ui_search_http_code: $ls_ui_search,
        admin_ui_root_http_code: $admin_ui_root,
        admin_ui_sources_http_code: $admin_ui_sources
      }
    }'
)"

if [[ "${JSON_ONLY}" -eq 1 ]]; then
  echo "${summary_json}"
else
  log ""
  log "Done. Use --json for a machine-readable summary suitable for agents or CI notes."
fi
