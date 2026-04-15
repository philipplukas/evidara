#!/usr/bin/env bash
set -euo pipefail

FRONTEND_URL="${EVIDARA_LEGAL_SEARCH_FRONTEND_URL:-http://localhost:3101}"
ADMIN_URL="${EVIDARA_CONTROL_PANEL_URL:-http://localhost:3100}"
API_URL="${EVIDARA_LEGAL_SEARCH_API_URL:-http://localhost:3102}"
OPENSEARCH_URL="${EVIDARA_OPENSEARCH_URL:-http://localhost:9200}"
DOCUMENT_SERVICE_URL="${EVIDARA_DOCUMENT_SERVICE_URL:-http://localhost:8090}"
WAIT_MODE="false"
TIMEOUT_SECONDS="${EVIDARA_CROSS_SURFACE_PREFLIGHT_TIMEOUT:-60}"

while [[ $# -gt 0 ]]; do
  case "$1" in
    --wait)
      WAIT_MODE="true"
      shift
      ;;
    --timeout)
      TIMEOUT_SECONDS="${2:?missing value for --timeout}"
      shift 2
      ;;
    -h|--help)
      cat <<'HELP'
Usage: scripts/preflight-cross-surface-live.sh [--wait] [--timeout SECONDS]

Checks the local cross-surface stack:
  - legal-search frontend
  - control-panel admin
  - legal-search API (/v1/search/context and /v1/search)
  - OpenSearch (informational)
  - Document Service (informational)

Environment overrides:
  EVIDARA_LEGAL_SEARCH_FRONTEND_URL
  EVIDARA_CONTROL_PANEL_URL
  EVIDARA_LEGAL_SEARCH_API_URL
  EVIDARA_OPENSEARCH_URL
  EVIDARA_DOCUMENT_SERVICE_URL
  EVIDARA_CROSS_SURFACE_PREFLIGHT_TIMEOUT
HELP
      exit 0
      ;;
    *)
      echo "Unknown argument: $1" >&2
      exit 1
      ;;
  esac
done

pass() {
  printf 'PASS %s\n' "$1"
}

fail() {
  printf 'FAIL %s\n' "$1" >&2
}

snippet_from() {
  local file="$1"
  tr '\n' ' ' <"$file" | sed 's/[[:space:]]\+/ /g' | cut -c1-220
}

probe_http() {
  local url="$1"
  local body_file="$2"

  local status
  status="$(curl -sS -L -o "$body_file" -w '%{http_code}' "$url" || true)"
  printf '%s' "$status"
}

check_required_endpoint() {
  local label="$1"
  local url="$2"
  local body_file
  body_file="$(mktemp)"

  local status
  status="$(probe_http "$url" "$body_file")"
  if [[ "$status" == "200" ]]; then
    pass "$label ($url)"
    rm -f "$body_file"
    return 0
  fi

  local snippet
  snippet="$(snippet_from "$body_file")"
  fail "$label ($url) -> HTTP ${status:-000}${snippet:+ | $snippet}"
  rm -f "$body_file"
  return 1
}

check_optional_endpoint() {
  local label="$1"
  local url="$2"
  local body_file
  body_file="$(mktemp)"

  local status
  status="$(probe_http "$url" "$body_file")"
  if [[ "$status" == "200" ]]; then
    pass "$label ($url)"
    rm -f "$body_file"
    return 0
  fi

  local snippet
  snippet="$(snippet_from "$body_file")"
  printf 'WARN %s (%s) -> HTTP %s%s\n' "$label" "$url" "${status:-000}" "${snippet:+ | $snippet}"
  rm -f "$body_file"
  return 0
}

run_checks_once() {
  local failures=0

  check_required_endpoint "Legal-search frontend" "$FRONTEND_URL" || failures=$((failures + 1))
  check_required_endpoint "Control-panel admin" "$ADMIN_URL" || failures=$((failures + 1))
  check_required_endpoint "Legal-search API search context" "${API_URL%/}/v1/search/context" || failures=$((failures + 1))
  check_required_endpoint "Legal-search API search" "${API_URL%/}/v1/search?q=probe&page=1&page_size=1" || failures=$((failures + 1))
  check_optional_endpoint "OpenSearch cluster" "${OPENSEARCH_URL%/}/_cluster/health"
  check_optional_endpoint "Document Service health" "${DOCUMENT_SERVICE_URL%/}/health"

  return "$failures"
}

if [[ "$WAIT_MODE" == "true" ]]; then
  deadline=$((SECONDS + TIMEOUT_SECONDS))
  while true; do
    if run_checks_once; then
      exit 0
    fi

    if (( SECONDS >= deadline )); then
      cat <<EOF >&2
Preflight timed out after ${TIMEOUT_SECONDS}s.

Usual fixes:
  1. Start the lean backend stack: ./scripts/dev-lean-search-stack.sh up
  2. Or run the split workflow:
     ./scripts/dev-lean-search-stack.sh up-split
     eval "\$(./scripts/dev-lean-search-stack.sh print-env)"
     cd legal-search/api && npm run dev
  3. Start the browser apps:
     npm run dev:cross-surface:live
EOF
      exit 1
    fi

    sleep 2
  done
fi

if run_checks_once; then
  exit 0
fi

cat <<'EOF' >&2
Cross-surface preflight failed.

Most common causes:
  - legal-search API is not running on localhost:3102
  - OpenSearch is not up, so the API cannot serve search endpoints
  - frontend/admin dev servers are not running on localhost:3101 / localhost:3100
EOF
exit 1
