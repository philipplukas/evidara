#!/usr/bin/env bash
# Bootstrap OpenSearch + file-backed DI lean fixture for TAR-89 local/staging-style checks,
# then (optionally) GET lean, replay projection, GET search — steps 1 & 2 from the runbook.
#
# Prereqs: Docker (optional, for OpenSearch), curl, jq; `uv` in PATH for --smoke-di;
# legal-search API running separately for replay/search phases unless you only run --bootstrap.
#
# Usage:
#   ./scripts/validate-tar89-metadata-local.sh --bootstrap
#   DOCUMENT_INTELLIGENCE_BASE_URL=http://127.0.0.1:8090 LEGAL_SEARCH_API_URL=http://127.0.0.1:3102 \
#     ./scripts/validate-tar89-metadata-local.sh --all
#
set -euo pipefail

ROOT="$(cd "$(dirname "${BASH_SOURCE[0]}")/.." && pwd)"
OS="${OPENSEARCH_NODE:-http://127.0.0.1:9200}"
OS="${OS%/}"
WRITE_INDEX="${OPENSEARCH_ALIAS_WRITE:-documents-write}"
READ_ALIAS="${OPENSEARCH_ALIAS_READ:-documents-read}"
DOC_ID="doc_01jq7bhgy7g0pkj4f1d03f8f8c"
CONTENT_DIR="$ROOT/scripts/fixtures/tar89-demo-content"
TEMPLATE="$ROOT/scripts/fixtures/tar89-document-processed.template.json"
REPLAY="$ROOT/scripts/replay-document-projection.sh"
# Generated from legal-search/api/src/core/opensearch/documents-index.mapping.ts.
MAPPING_JSON="$ROOT/scripts/opensearch/documents-index.mapping.json"

usage() {
  cat <<EOF
Usage: $0 [--bootstrap] [--smoke-di] [--replay] [--search] [--all]

  --bootstrap   Wait for OpenSearch, create indices + alias, index a STALE projection doc,
                ensure DI lean fixture exists under scripts/fixtures/tar89-demo-content/.
  --smoke-di    Start Document Service on 127.0.0.1:\${DOCUMENT_SERVICE_PORT:-8090} (uv run), GET /lean, stop.
  --replay      POST document.processed via replay-document-projection.sh (needs LEGAL_SEARCH_API_URL).
  --search      GET /v1/search (needs LEGAL_SEARCH_API_URL).
  --all         bootstrap + smoke-di + replay + search

Env:
  OPENSEARCH_NODE (default $OS)
  OPENSEARCH_ALIAS_WRITE (default documents-write)
  OPENSEARCH_ALIAS_READ (default documents-read)
  DOCUMENT_INTELLIGENCE_BASE_URL — for --replay/--search API process (you must export when starting the API)
  DOCUMENT_SERVICE_AUTH_MODE — optional note for evidence output, e.g. none, bearer, file-backed-bearer
  LEGAL_SEARCH_API_URL — default http://127.0.0.1:3102
  DOCUMENT_SERVICE_PORT — default 8090 for --smoke-di

Recommended API dev env (terminal 2):
  cd legal-search/api && \\
    OPENSEARCH_NODE=$OS \\
    OPENSEARCH_ALIAS_READ=$READ_ALIAS \\
    OPENSEARCH_ALIAS_WRITE=$WRITE_INDEX \\
    DOCUMENT_INTELLIGENCE_BASE_URL=http://127.0.0.1:8090 \\
    npm run dev
EOF
}

wait_for_os() {
  local i status
  # Do not use wait_for_status=… on this URL: it long-polls and can leave curl stuck past tool timeouts.
  for i in $(seq 1 60); do
    status="$(
      curl -sS -m 5 "$OS/_cluster/health" 2>/dev/null | jq -r '.status // empty' || true
    )"
    if [[ "$status" == "yellow" || "$status" == "green" ]]; then
      return 0
    fi
    echo "  waiting for OpenSearch at $OS (status=${status:-none}, $i/60)..."
    sleep 1
  done
  echo "error: OpenSearch not reachable at $OS (start: docker compose --profile search up -d)" >&2
  return 1
}

ensure_projection_history_index() {
  local idx="projection-history"
  local code
  code="$(curl -sS -m 15 -o /dev/null -w "%{http_code}" "$OS/$idx" || echo 000)"
  if [[ "$code" == "200" ]]; then
    return 0
  fi
  curl -fsS -m 30 -X PUT "$OS/$idx" -H 'Content-Type: application/json' -d '{
    "settings": {"number_of_shards": 1, "number_of_replicas": 0},
    "mappings": {
      "properties": {
        "event_id": {"type": "keyword"},
        "event_type": {"type": "keyword"},
        "document_id": {"type": "keyword"},
        "document_revision": {"type": "integer"},
        "processing_manifest_id": {"type": "keyword"},
        "run_id": {"type": "keyword"},
        "occurred_at": {"type": "date"},
        "status": {"type": "keyword"},
        "notes": {"type": "text"}
      }
    }
  }' >/dev/null
  echo "  created index $idx"
}

ensure_documents_index() {
  local code
  code="$(curl -sS -m 15 -o /dev/null -w "%{http_code}" "$OS/$WRITE_INDEX" || echo 000)"
  if [[ "$code" == "200" ]]; then
    return 0
  fi
  # Apply the CANONICAL mapping, never a copy of it (#675). This function used
  # to inline a hand-maintained mapping that had drifted from
  # `legal-search/api/src/core/opensearch/documents-index.mapping.ts`: bare
  # `keyword` facet fields with no `.keyword` sub-field, and no
  # `jurisdiction_ids` / `authority_ids` at all. Aggregating a field that does
  # not exist is not an error in OpenSearch — it silently returns empty buckets
  # — so the index this created served a permanently dead facet rail and
  # `authority_id` filters that matched nothing, while every test stayed green.
  #
  # MAPPING_JSON is generated from that TypeScript source of truth and
  # drift-gated by `documents-index.mapping-json.spec.ts`. Regenerate with
  # `cd legal-search/api && npm run mapping:generate`. The `$comment` banner is
  # stripped because OpenSearch rejects unknown top-level keys on create-index.
  if [[ ! -f "$MAPPING_JSON" ]]; then
    echo "error: missing $MAPPING_JSON — run 'cd legal-search/api && npm run mapping:generate'" >&2
    exit 1
  fi
  jq 'del(."$comment")' "$MAPPING_JSON" \
    | curl -fsS -m 30 -X PUT "$OS/$WRITE_INDEX" -H 'Content-Type: application/json' -d @- >/dev/null
  echo "  created index $WRITE_INDEX from canonical mapping"
}

ensure_read_alias() {
  if curl -fsS -m 10 "$OS/_alias/$READ_ALIAS" 2>/dev/null | jq -e --arg w "$WRITE_INDEX" --arg a "$READ_ALIAS" \
    'to_entries[] | select(.key==$w) | .value.aliases[$a]' >/dev/null 2>&1; then
    echo "  alias $READ_ALIAS -> $WRITE_INDEX (already)"
    return 0
  fi
  curl -fsS -m 30 -X POST "$OS/_aliases" -H 'Content-Type: application/json' -d "{
    \"actions\": [{\"add\": {\"index\": \"$WRITE_INDEX\", \"alias\": \"$READ_ALIAS\"}}]
  }" >/dev/null
  echo "  alias $READ_ALIAS -> $WRITE_INDEX"
}

index_stale_projection() {
  local body
  body="$(jq -n \
    --arg id "$DOC_ID" \
    --arg title "Document $DOC_ID" \
    --arg processed "$(date -u +%Y-%m-%dT%H:%M:%SZ)" \
    '{
      document_id: $id,
      title: $title,
      jurisdiction: "CH",
      document_type: "unknown",
      language: "de",
      effective_date: "2020-01-01",
      sections_count: 0,
      citations_count: 0,
      related_decisions_count: 0,
      related_commentary_count: 0,
      processed_at: $processed,
      content_preview: "stale seed for TAR-89 replay"
    }')"
  curl -fsS -m 60 -X PUT "$OS/$WRITE_INDEX/_doc/$DOC_ID?refresh=wait_for" \
    -H 'Content-Type: application/json' \
    -d "$body" >/dev/null
  echo "  indexed stale projection $DOC_ID (title placeholder, type unknown)"
}

do_bootstrap() {
  echo "== Bootstrap OpenSearch + lean fixture =="
  if ! command -v jq >/dev/null 2>&1; then
    echo "error: jq is required (e.g. brew install jq)" >&2
    exit 1
  fi
  wait_for_os
  ensure_projection_history_index
  ensure_documents_index
  ensure_read_alias
  index_stale_projection
  if [[ ! -f "$CONTENT_DIR/$DOC_ID.json" ]]; then
    echo "error: missing lean fixture $CONTENT_DIR/$DOC_ID.json" >&2
    exit 1
  fi
  echo "  DI lean file: $CONTENT_DIR/$DOC_ID.json"
  echo ""
  echo "Start Document Service (terminal 1), e.g.:"
  echo "  cd $ROOT/document-intelligence && \\"
  echo "    DOCUMENT_SERVICE_CONTENT_DIR=$CONTENT_DIR DOCUMENT_SERVICE_PORT=8090 uv run document_intelligence_document_service"
  echo ""
  echo "Start legal-search API (terminal 2) with DOCUMENT_INTELLIGENCE_BASE_URL=http://127.0.0.1:8090"
  echo "  and OPENSEARCH_ALIAS_READ=$READ_ALIAS OPENSEARCH_ALIAS_WRITE=$WRITE_INDEX OPENSEARCH_NODE=$OS"
  echo "  Optional for sign-off notes: export DOCUMENT_SERVICE_AUTH_MODE=none"
}

do_smoke_di() {
  local port="${DOCUMENT_SERVICE_PORT:-8090}"
  local base="http://127.0.0.1:$port"
  local auth_mode="none"
  if [[ -n "${DOCUMENT_SERVICE_BEARER_TOKEN:-}" ]]; then
    auth_mode="bearer"
  fi
  echo "== Smoke Document Service (GET /lean) =="
  echo "  Document Service base URL: $base"
  echo "  Document Service auth mode: $auth_mode"
  if ! command -v uv >/dev/null 2>&1; then
    echo "error: uv not found; run Document Service manually" >&2
    exit 1
  fi
  (
    cd "$ROOT/document-intelligence"
    export DOCUMENT_SERVICE_CONTENT_DIR="$CONTENT_DIR"
    export DOCUMENT_SERVICE_PORT="$port"
    uv run document_intelligence_document_service
  ) &
  local pid=$!
  trap 'kill "$pid" 2>/dev/null || true' RETURN
  sleep 3
  curl -fsS "$base/v1/documents/$DOC_ID/lean" | jq '{title, document_type, metadata}'
  echo "  OK lean response"
  kill "$pid" 2>/dev/null || true
  wait "$pid" 2>/dev/null || true
  trap - RETURN
}

require_document_service_context() {
  local ds="${DOCUMENT_INTELLIGENCE_BASE_URL:-}"
  if [[ -z "$ds" ]]; then
    echo "error: DOCUMENT_INTELLIGENCE_BASE_URL must be exported for --replay/--search so the run records the intended Document Service origin" >&2
    exit 1
  fi
  ds="${ds%/}"
  echo "  Expected Document Service base URL: $ds"
  echo "  Declared Document Service auth mode: ${DOCUMENT_SERVICE_AUTH_MODE:-unset (export DOCUMENT_SERVICE_AUTH_MODE=none|bearer|file-backed-bearer)}"
}

do_replay() {
  local api="${LEGAL_SEARCH_API_URL:-http://127.0.0.1:3102}"
  api="${api%/}"
  echo "== Replay projection =="
  require_document_service_context
  LEGAL_SEARCH_API_URL="$api" "$REPLAY" "$TEMPLATE"
}

do_search() {
  local api="${LEGAL_SEARCH_API_URL:-http://127.0.0.1:3102}"
  api="${api%/}"
  echo "== Search API (expect updated title after replay) =="
  require_document_service_context
  curl -fsS "$api/v1/search?q=Bundesgericht&page_size=5" | jq ".results[] | select(.id==\"$DOC_ID\") | {id, type, title, metadataRows}"
}

DO_BOOT=0
DO_SMOKE=0
DO_REPLAY=0
DO_SEARCH=0

for arg in "${@:-}"; do
  case "$arg" in
    --bootstrap) DO_BOOT=1 ;;
    --smoke-di) DO_SMOKE=1 ;;
    --replay) DO_REPLAY=1 ;;
    --search) DO_SEARCH=1 ;;
    --all) DO_BOOT=1 DO_SMOKE=1 DO_REPLAY=1 DO_SEARCH=1 ;;
    -h|--help) usage; exit 0 ;;
    *)
      echo "unknown option: $arg" >&2
      usage >&2
      exit 1
      ;;
  esac
done

if [[ $DO_BOOT$DO_SMOKE$DO_REPLAY$DO_SEARCH == 0000 ]]; then
  usage >&2
  exit 1
fi

[[ "$DO_BOOT" == 1 ]] && do_bootstrap
[[ "$DO_SMOKE" == 1 ]] && do_smoke_di
[[ "$DO_REPLAY" == 1 ]] && do_replay
[[ "$DO_SEARCH" == 1 ]] && do_search

echo ""
echo "Done. Record DOCUMENT_INTELLIGENCE_BASE_URL and DOCUMENT_SERVICE_AUTH_MODE with the replay result."
echo "If title in search is still the stale placeholder, confirm API has DOCUMENT_INTELLIGENCE_BASE_URL"
echo "and replay returned {\"status\":\"applied\"}."
