#!/usr/bin/env bash
# One entry point for local search + DI lean + TAR-89-style checks (no manual copy-paste).
#
# Usage:
#   ./scripts/dev-lean-search-stack.sh up        # Docker Compose profile `lean-stack`: OS + DI + bootstrap + API (port 3102)
#   ./scripts/dev-lean-search-stack.sh up-split # Legacy: only search+lean profiles + host bootstrap (needs local jq)
#   ./scripts/dev-lean-search-stack.sh print-env # Exports for host `npm run dev` (when not using API container)
#   ./scripts/dev-lean-search-stack.sh replay    # Replay projection + GET search (API on 3102, host or container)
#   ./scripts/dev-lean-search-stack.sh smoke     # curl Document Service /health + /lean
#   ./scripts/dev-lean-search-stack.sh down      # Stop lean-stack (or up-split) containers
#
set -euo pipefail

ROOT="$(cd "$(dirname "${BASH_SOURCE[0]}")/.." && pwd)"
OS_PORT="${EVIDARA_OPENSEARCH_HTTP_PORT:-9200}"
DS_PORT="${EVIDARA_DOCUMENT_SERVICE_PORT:-8090}"
DOC_ID="doc_01jq7bhgy7g0pkj4f1d03f8f8c"
TEMPLATE="$ROOT/scripts/fixtures/tar89-document-processed.template.json"

compose() {
  docker compose -f "$ROOT/docker-compose.yml" "$@"
}

cmd="${1:-help}"

case "$cmd" in
  up)
    echo "Starting lean-stack (OpenSearch + Document Service + bootstrap + legal-search-api-lean)..."
    compose --profile lean-stack up -d --build
    echo ""
    echo "URLs:"
    echo "  Legal-search API: http://127.0.0.1:${EVIDARA_LEGAL_SEARCH_API_PORT:-3102}"
    echo "  Document Service: http://127.0.0.1:${DS_PORT}"
    echo "  OpenSearch:       http://127.0.0.1:${OS_PORT}"
    echo ""
    echo "Wait until API health is OK, then:"
    echo "  ./scripts/dev-lean-search-stack.sh replay"
    echo ""
    echo "Host hot-reload API instead of container: use ./scripts/dev-lean-search-stack.sh up-split, then print-env + npm run dev"
    ;;
  up-split)
    if ! command -v jq >/dev/null 2>&1; then
      echo "error: jq is required (e.g. brew install jq)" >&2
      exit 1
    fi
    echo "Starting OpenSearch + Document Service only (profiles: search, lean), bootstrap on host..."
    compose --profile search --profile lean up -d --build
    echo "Waiting for OpenSearch on port $OS_PORT..."
    export OPENSEARCH_NODE="http://127.0.0.1:${OS_PORT}"
    for i in $(seq 1 60); do
      st="$(curl -sS -m 5 "$OPENSEARCH_NODE/_cluster/health" 2>/dev/null | jq -r '.status // empty' || true)"
      if [[ "$st" == "yellow" || "$st" == "green" ]]; then
        break
      fi
      sleep 1
      echo "  ... still waiting ($i/60, status=${st:-none})"
    done
    OPENSEARCH_NODE="$OPENSEARCH_NODE" "$ROOT/scripts/validate-tar89-metadata-local.sh" --bootstrap
    echo ""
    echo "Stack is up (no API container). Run BFF on host:"
    echo "  eval \"\$(./scripts/dev-lean-search-stack.sh print-env)\""
    echo "  cd legal-search/api && npm run dev"
    ;;
  print-env)
    cat <<EOF
export OPENSEARCH_NODE="http://127.0.0.1:${OS_PORT}"
export OPENSEARCH_ALIAS_READ="documents-read"
export OPENSEARCH_ALIAS_WRITE="documents-write"
export DOCUMENT_INTELLIGENCE_BASE_URL="http://127.0.0.1:${DS_PORT}"
EOF
    ;;
  smoke)
    echo "GET Document Service /health ..."
    curl -fsS "http://127.0.0.1:${DS_PORT}/health" | jq .
    echo "GET lean ..."
    curl -fsS "http://127.0.0.1:${DS_PORT}/v1/documents/${DOC_ID}/lean" | jq '{title, document_type, metadata}'
    ;;
  replay)
    export LEGAL_SEARCH_API_URL="${LEGAL_SEARCH_API_URL:-http://127.0.0.1:3102}"
    "$ROOT/scripts/replay-document-projection.sh" "$TEMPLATE"
    echo ""
    echo "Search hit (API must use same OpenSearch + aliases as bootstrap):"
    curl -fsS "${LEGAL_SEARCH_API_URL%/}/v1/search?q=Bundesgericht&page_size=5" \
      | jq ".results[] | select(.id==\"$DOC_ID\") | {id, type, title, metadataRows}"
    ;;
  bootstrap)
    OPENSEARCH_NODE="${OPENSEARCH_NODE:-http://127.0.0.1:${OS_PORT}}" \
      "$ROOT/scripts/validate-tar89-metadata-local.sh" --bootstrap
    ;;
  down)
    echo "Stopping lean-stack (and removing its containers)..."
    compose --profile lean-stack down
    echo "If you used up-split, also run: docker compose --profile search --profile lean down"
    ;;
  help|-h|--help)
    cat <<'HELP'
Commands:
  up         docker compose --profile lean-stack (OpenSearch + DI + init + API on 3102)
  up-split   search+lean only, bootstrap via host script (for npm run dev on host)
  print-env  shell exports for host API when using up-split
  smoke      curl Document Service /health and /lean
  replay     POST document.processed + GET /v1/search
  bootstrap  Re-run validate-tar89-metadata-local.sh --bootstrap against OPENSEARCH_NODE
  down       docker compose --profile lean-stack down
  help       This message
HELP
    ;;
  *)
    echo "unknown command: $cmd" >&2
    exec "$0" help
    ;;
esac
