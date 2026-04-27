#!/usr/bin/env bash
# Hetzner staging smoke: correction -> apply -> Temporal rescore -> metrics.
#
# Defaults target the rocky-agents staging cluster through kubectl port-forward.
# To target an already reachable API, set:
#   PLATFORM_CONTROL_BASE_URL=http://host:port
#   PLATFORM_CONTROL_API_KEY=...
set -euo pipefail

DEFAULT_DOCUMENT_ID="doc_6vfta1cd5xy642g7eb59j8wkfm"

K8S_NAMESPACE="${K8S_NAMESPACE:-evidare-staging}"
K8S_SERVICE="${K8S_SERVICE:-platform-control-api}"
K8S_SECRET="${K8S_SECRET:-evidara-platform-control-api-keys}"
K8S_SECRET_KEY="${K8S_SECRET_KEY:-PLATFORM_CONTROL_OPERATOR_API_KEY}"
LOCAL_PORT="${LOCAL_PORT:-18080}"
DOCUMENT_ID="${DOCUMENT_ID:-$DEFAULT_DOCUMENT_ID}"
POLL_ATTEMPTS="${POLL_ATTEMPTS:-60}"
POLL_SECONDS="${POLL_SECONDS:-2}"

PORT_FORWARD_PID=""
PORT_FORWARD_LOG=""

cleanup() {
  if [[ -n "$PORT_FORWARD_PID" ]]; then
    kill "$PORT_FORWARD_PID" >/dev/null 2>&1 || true
  fi
  if [[ -n "$PORT_FORWARD_LOG" ]]; then
    rm -f "$PORT_FORWARD_LOG"
  fi
}
trap cleanup EXIT

need() {
  if ! command -v "$1" >/dev/null 2>&1; then
    echo "missing required command: $1" >&2
    exit 127
  fi
}

need curl
need jq

if [[ -z "${PLATFORM_CONTROL_BASE_URL:-}" ]]; then
  need kubectl
  PLATFORM_CONTROL_BASE_URL="http://127.0.0.1:${LOCAL_PORT}"
  PORT_FORWARD_LOG="$(mktemp)"
  kubectl port-forward -n "$K8S_NAMESPACE" "svc/${K8S_SERVICE}" "${LOCAL_PORT}:8080" \
    >"$PORT_FORWARD_LOG" 2>&1 &
  PORT_FORWARD_PID="$!"
  for _ in $(seq 1 30); do
    if curl -fsS "${PLATFORM_CONTROL_BASE_URL}/health" >/dev/null 2>&1; then
      break
    fi
    if ! kill -0 "$PORT_FORWARD_PID" >/dev/null 2>&1; then
      echo "kubectl port-forward exited unexpectedly:" >&2
      cat "$PORT_FORWARD_LOG" >&2
      exit 1
    fi
    sleep 1
  done
fi

if [[ -z "${PLATFORM_CONTROL_API_KEY:-}" ]]; then
  need kubectl
  PLATFORM_CONTROL_API_KEY="$(
    kubectl get secret "$K8S_SECRET" -n "$K8S_NAMESPACE" \
      -o "jsonpath={.data.${K8S_SECRET_KEY}}" | base64 -d
  )"
fi

api() {
  local method="$1"
  local path="$2"
  local data="${3:-}"
  local -a args=(
    -fsS
    -X "$method"
    "${PLATFORM_CONTROL_BASE_URL}${path}"
    -H "X-API-Key: ${PLATFORM_CONTROL_API_KEY}"
    -H "Content-Type: application/json"
  )
  if [[ -n "$data" ]]; then
    args+=(--data "$data")
  fi
  curl "${args[@]}"
}

health="$(curl -fsS "${PLATFORM_CONTROL_BASE_URL}/health")"
echo "$health" | jq -e '.status == "ok"' >/dev/null

before_metrics="$(api GET /v1/corrections/metrics)"
before_applied="$(echo "$before_metrics" | jq -r '.rescore_outcomes.applied_total // 0')"
before_changed="$(echo "$before_metrics" | jq -r '.rescore_outcomes.changed // 0')"
before_unchanged="$(echo "$before_metrics" | jq -r '.rescore_outcomes.unchanged // 0')"
before_failed="$(echo "$before_metrics" | jq -r '.rescore_outcomes.failed // 0')"

create_payload="$(
  jq -cn --arg document_id "$DOCUMENT_ID" '{
    target_entity_type: "document",
    target_entity_id: $document_id,
    correction_type: "rescore_request",
    payload: {
      reason_code: "hetzner_staging_seed_smoke",
      requested_priority: "normal"
    },
    rationale: "Hetzner staging seeded DI surface smoke."
  }'
)"
created="$(api POST /v1/corrections "$create_payload")"
correction_id="$(echo "$created" | jq -r '.correction_id')"
operator_id="$(echo "$created" | jq -r '.operator_id')"

applied="$(api PATCH "/v1/corrections/${correction_id}" '{"status":"applied","rationale":"Hetzner staging smoke approved."}')"
workflow_id="$(echo "$applied" | jq -r '.payload.triggered_workflow_id // empty')"
if [[ -z "$workflow_id" ]]; then
  echo "applied correction did not include payload.triggered_workflow_id" >&2
  echo "$applied" | jq . >&2
  exit 1
fi

final=""
for _ in $(seq 1 "$POLL_ATTEMPTS"); do
  fetched="$(api GET "/v1/corrections/${correction_id}")"
  outcome="$(echo "$fetched" | jq -r '.payload.rescore_outcome // empty')"
  if [[ -n "$outcome" ]]; then
    final="$fetched"
    break
  fi
  sleep "$POLL_SECONDS"
done

if [[ -z "$final" ]]; then
  echo "timed out waiting for rescore outcome for ${correction_id}" >&2
  exit 1
fi

outcome="$(echo "$final" | jq -r '.payload.rescore_outcome')"
if [[ "$outcome" != "changed" && "$outcome" != "unchanged" ]]; then
  echo "expected rescore outcome changed|unchanged, got: ${outcome}" >&2
  echo "$final" | jq . >&2
  exit 1
fi

after_metrics="$(api GET /v1/corrections/metrics)"
after_applied="$(echo "$after_metrics" | jq -r '.rescore_outcomes.applied_total // 0')"
after_changed="$(echo "$after_metrics" | jq -r '.rescore_outcomes.changed // 0')"
after_unchanged="$(echo "$after_metrics" | jq -r '.rescore_outcomes.unchanged // 0')"
after_failed="$(echo "$after_metrics" | jq -r '.rescore_outcomes.failed // 0')"

if [[ "$after_applied" -ne $((before_applied + 1)) ]]; then
  echo "expected applied_total to increment by 1 (${before_applied} -> ${after_applied})" >&2
  exit 1
fi
case "$outcome" in
  changed)
    if [[ "$after_changed" -ne $((before_changed + 1)) ]]; then
      echo "expected changed bucket to increment by 1" >&2
      exit 1
    fi
    ;;
  unchanged)
    if [[ "$after_unchanged" -ne $((before_unchanged + 1)) ]]; then
      echo "expected unchanged bucket to increment by 1" >&2
      exit 1
    fi
    ;;
esac
if [[ "$after_failed" -ne "$before_failed" ]]; then
  echo "failed bucket changed unexpectedly (${before_failed} -> ${after_failed})" >&2
  exit 1
fi

jq -n \
  --arg status "ok" \
  --arg document_id "$DOCUMENT_ID" \
  --arg correction_id "$correction_id" \
  --arg operator_id "$operator_id" \
  --arg workflow_id "$workflow_id" \
  --arg outcome "$outcome" \
  --argjson before "$before_metrics" \
  --argjson after "$after_metrics" \
  '{
    status: $status,
    document_id: $document_id,
    correction_id: $correction_id,
    operator_id: $operator_id,
    triggered_workflow_id: $workflow_id,
    rescore_outcome: $outcome,
    metrics_before: $before.rescore_outcomes,
    metrics_after: $after.rescore_outcomes
  }'
