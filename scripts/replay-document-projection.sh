#!/usr/bin/env bash
# Replay a document.processed event against legal-search so ProjectionsService re-fetches lean
# from Document Service and upserts OpenSearch. Each POST must use a NEW event_id (history dedup).
#
# Usage:
#   LEGAL_SEARCH_API_URL=http://127.0.0.1:3102 ./scripts/replay-document-projection.sh path/to/event.json
#
# Env:
#   LEGAL_SEARCH_API_URL — BFF base URL (default http://127.0.0.1:3102)
#   CURL_AUTH — optional, e.g. '-H "Authorization: Bearer …"' for protected APIs
#
# Stale guard: if the API returns status "stale", bump payload.document_revision to be >= the
# latest revision already stored for that document_id (see ProjectionsService).
#
set -euo pipefail

BASE_URL="${LEGAL_SEARCH_API_URL:-http://127.0.0.1:3102}"
BASE_URL="${BASE_URL%/}"

EVENT_FILE="${1:?Usage: $0 <document-processed.json>}"
if [[ ! -f "$EVENT_FILE" ]]; then
  echo "error: file not found: $EVENT_FILE" >&2
  exit 1
fi

if ! command -v jq >/dev/null 2>&1; then
  echo "error: jq is required" >&2
  exit 1
fi

NEW_ID="evt_replay_$(date -u +%Y%m%d%H%M%S)_$(openssl rand -hex 4 2>/dev/null || echo "$RANDOM")"
OCCURRED="$(date -u +%Y-%m-%dT%H:%M:%SZ)"
TMP="$(mktemp)"
trap 'rm -f "$TMP"' EXIT

jq --arg id "$NEW_ID" --arg ts "$OCCURRED" '.event_id = $id | .occurred_at = $ts' "$EVENT_FILE" >"$TMP"

echo "Posting document.processed event_id=$NEW_ID to $BASE_URL/v1/projections/events/document-processed" >&2
# shellcheck disable=SC2086
curl -sS ${CURL_AUTH:-} -X POST "$BASE_URL/v1/projections/events/document-processed" \
  -H 'Content-Type: application/json' \
  -d @"$TMP"
echo
