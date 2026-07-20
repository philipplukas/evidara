#!/usr/bin/env bash
# Replay messages from a Pub/Sub dead-letter queue (DLQ) to the original topic.
#
# Usage:
#   ./scripts/replay-dlq.sh SUBSCRIPTION_NAME TOPIC_NAME [--project PROJECT_ID] [--limit N] [--dry-run]
#
# Examples:
#   # Replay up to 10 messages from DI DLQ
#   ./scripts/replay-dlq.sh document-intelligence-artifact-bundle-available-dlq-sub \
#     artifact-bundle-available --project evidara-dev --limit 10
#
#   # Dry-run: inspect messages without replaying
#   ./scripts/replay-dlq.sh legal-search-document-processed-dlq-sub \
#     document-processed --project evidara-dev --dry-run
#
# See also: docs/runbooks/dlq-triage-and-replay.md

set -euo pipefail

SUBSCRIPTION="${1:?Usage: $0 SUBSCRIPTION TOPIC [--project PROJECT] [--limit N] [--dry-run]}"
TOPIC="${2:?Usage: $0 SUBSCRIPTION TOPIC [--project PROJECT] [--limit N] [--dry-run]}"
shift 2

PROJECT=""
LIMIT=10
DRY_RUN=false

while [[ $# -gt 0 ]]; do
  case "$1" in
    --project)  PROJECT="$2"; shift 2 ;;
    --limit)    LIMIT="$2"; shift 2 ;;
    --dry-run)  DRY_RUN=true; shift ;;
    *)          echo "Unknown option: $1" >&2; exit 1 ;;
  esac
done

# Deliberately unquoted at the call sites below: PROJECT_FLAG is either empty (no
# flag at all) or a single `--project=x` argument, and quoting an empty string
# would pass gcloud a stray empty argument. See check-e2e-spec-coverage.sh:86 for
# the same pattern.
PROJECT_FLAG=""
if [[ -n "$PROJECT" ]]; then
  PROJECT_FLAG="--project=$PROJECT"
fi

echo "=== DLQ Replay ==="
echo "Source subscription: $SUBSCRIPTION"
echo "Target topic:        $TOPIC"
echo "Limit:               $LIMIT"
echo "Dry run:             $DRY_RUN"
echo ""

# Pull messages without ack
# shellcheck disable=SC2086 # intentional: PROJECT_FLAG is empty-or-one-flag
MESSAGES=$(gcloud pubsub subscriptions pull "$SUBSCRIPTION" \
  $PROJECT_FLAG \
  --limit="$LIMIT" \
  --auto-ack=false \
  --format=json 2>/dev/null || echo "[]")

COUNT=$(echo "$MESSAGES" | python3 -c "import sys,json; print(len(json.load(sys.stdin)))" 2>/dev/null || echo "0")

if [[ "$COUNT" == "0" ]]; then
  echo "No messages found in $SUBSCRIPTION"
  exit 0
fi

echo "Found $COUNT message(s) in DLQ"
echo ""

REPLAYED=0
FAILED=0

for i in $(seq 0 $((COUNT - 1))); do
  MESSAGE_ID=$(echo "$MESSAGES" | python3 -c "import sys,json; print(json.load(sys.stdin)[$i].get('message',{}).get('messageId','unknown'))")
  DATA=$(echo "$MESSAGES" | python3 -c "
import sys, json, base64
msg = json.load(sys.stdin)[$i]
data = msg.get('message',{}).get('data','')
print(base64.b64decode(data).decode('utf-8'))
" 2>/dev/null || echo "")

  echo "--- Message $((i+1))/$COUNT (ID: $MESSAGE_ID) ---"

  if [[ -z "$DATA" ]]; then
    echo "  SKIP: empty payload"
    ((FAILED++)) || true
    continue
  fi

  # Truncated preview
  PREVIEW=$(echo "$DATA" | head -c 200)
  echo "  Payload: ${PREVIEW}..."

  if [[ "$DRY_RUN" == "true" ]]; then
    echo "  [DRY RUN] Would republish to $TOPIC"
    continue
  fi

  # Republish to original topic
  # shellcheck disable=SC2086 # intentional: PROJECT_FLAG is empty-or-one-flag
  if gcloud pubsub topics publish "$TOPIC" \
    $PROJECT_FLAG \
    --message="$DATA" >/dev/null 2>&1; then
    echo "  ✓ Republished to $TOPIC"
    ((REPLAYED++)) || true
  else
    echo "  ✗ Failed to republish"
    ((FAILED++)) || true
  fi
done

echo ""
echo "=== Summary ==="
echo "Total:    $COUNT"
echo "Replayed: $REPLAYED"
echo "Failed:   $FAILED"

if [[ "$DRY_RUN" == "false" && "$REPLAYED" -gt 0 ]]; then
  echo ""
  echo "NOTE: Messages have been republished but NOT acked from the DLQ."
  echo "After confirming successful processing, purge the DLQ:"
  echo "  gcloud pubsub subscriptions seek $SUBSCRIPTION $PROJECT_FLAG --time=now"
fi
