#!/usr/bin/env bash
set -euo pipefail

ROOT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")/.." && pwd)"

usage() {
  cat <<'EOF'
Usage: bash scripts/local-vertical-slice.sh <command> [mode]

Commands:
  up        Start local runtime dependencies
  up-all    Start local runtime dependencies plus app services via Compose
  down      Stop local runtime dependencies
  down-all  Stop app services and local runtime dependencies started via Compose
  status    Show dependency container status
  status-all Show app + dependency container status from local Compose setup
  check-all Validate full local compose stack endpoints
  env       Print local env variables used by runtime services
  help      Show this message

Modes:
  lite      postgres only (lowest RAM)
  search    postgres + opensearch (default; recommended for search API work)
  full      postgres + opensearch + pubsub emulator
EOF
}

normalize_mode() {
  local mode="${1:-search}"
  case "$mode" in
    lite|search|full)
      echo "$mode"
      ;;
    *)
      echo "Invalid mode: $mode" >&2
      usage >&2
      exit 1
      ;;
  esac
}

compose_up() {
  local mode
  mode="$(normalize_mode "${1:-search}")"
  case "$mode" in
    lite)
      (cd "$ROOT_DIR" && docker compose up -d postgres)
      ;;
    search)
      (cd "$ROOT_DIR" && docker compose --profile search up -d)
      ;;
    full)
      (cd "$ROOT_DIR" && docker compose --profile full up -d)
      ;;
  esac
}

compose_up_all() {
  local mode
  mode="$(normalize_mode "${1:-search}")"
  local postgres_port="${EVIDARA_POSTGRES_HOST_PORT:-15432}"
  local os_http_port="${EVIDARA_OPENSEARCH_HTTP_PORT:-19200}"
  local os_metrics_port="${EVIDARA_OPENSEARCH_METRICS_PORT:-19600}"
  local pubsub_port="${EVIDARA_PUBSUB_HOST_PORT:-18681}"
  case "$mode" in
    lite)
      echo "up-all requires search or full mode (OpenSearch is required)." >&2
      exit 1
      ;;
    search)
      (cd "$ROOT_DIR" && EVIDARA_POSTGRES_HOST_PORT="$postgres_port" EVIDARA_OPENSEARCH_HTTP_PORT="$os_http_port" EVIDARA_OPENSEARCH_METRICS_PORT="$os_metrics_port" EVIDARA_PUBSUB_HOST_PORT="$pubsub_port" docker compose -f docker-compose.yml -f docker-compose.local.yml --profile search --profile apps up -d --build)
      ;;
    full)
      (cd "$ROOT_DIR" && EVIDARA_POSTGRES_HOST_PORT="$postgres_port" EVIDARA_OPENSEARCH_HTTP_PORT="$os_http_port" EVIDARA_OPENSEARCH_METRICS_PORT="$os_metrics_port" EVIDARA_PUBSUB_HOST_PORT="$pubsub_port" docker compose -f docker-compose.yml -f docker-compose.local.yml --profile full --profile apps up -d --build)
      ;;
  esac
}

compose_down() {
  local mode
  mode="$(normalize_mode "${1:-search}")"
  case "$mode" in
    lite)
      (cd "$ROOT_DIR" && docker compose stop postgres)
      ;;
    search)
      (cd "$ROOT_DIR" && docker compose stop postgres opensearch)
      ;;
    full)
      (cd "$ROOT_DIR" && docker compose stop postgres opensearch pubsub)
      ;;
  esac
}

compose_down_all() {
  local mode
  mode="$(normalize_mode "${1:-search}")"
  local postgres_port="${EVIDARA_POSTGRES_HOST_PORT:-15432}"
  local os_http_port="${EVIDARA_OPENSEARCH_HTTP_PORT:-19200}"
  local os_metrics_port="${EVIDARA_OPENSEARCH_METRICS_PORT:-19600}"
  local pubsub_port="${EVIDARA_PUBSUB_HOST_PORT:-18681}"
  case "$mode" in
    lite)
      echo "down-all is only applicable to search/full app compose mode." >&2
      exit 1
      ;;
    search)
      (cd "$ROOT_DIR" && EVIDARA_POSTGRES_HOST_PORT="$postgres_port" EVIDARA_OPENSEARCH_HTTP_PORT="$os_http_port" EVIDARA_OPENSEARCH_METRICS_PORT="$os_metrics_port" EVIDARA_PUBSUB_HOST_PORT="$pubsub_port" docker compose -f docker-compose.yml -f docker-compose.local.yml --profile search --profile apps stop)
      ;;
    full)
      (cd "$ROOT_DIR" && EVIDARA_POSTGRES_HOST_PORT="$postgres_port" EVIDARA_OPENSEARCH_HTTP_PORT="$os_http_port" EVIDARA_OPENSEARCH_METRICS_PORT="$os_metrics_port" EVIDARA_PUBSUB_HOST_PORT="$pubsub_port" docker compose -f docker-compose.yml -f docker-compose.local.yml --profile full --profile apps stop)
      ;;
  esac
}

compose_status() {
  local mode
  mode="$(normalize_mode "${1:-search}")"
  case "$mode" in
    lite)
      (cd "$ROOT_DIR" && docker compose ps postgres)
      ;;
    search)
      (cd "$ROOT_DIR" && docker compose ps postgres opensearch)
      ;;
    full)
      (cd "$ROOT_DIR" && docker compose ps postgres opensearch pubsub)
      ;;
  esac
}

compose_status_all() {
  local mode
  mode="$(normalize_mode "${1:-search}")"
  local postgres_port="${EVIDARA_POSTGRES_HOST_PORT:-15432}"
  local os_http_port="${EVIDARA_OPENSEARCH_HTTP_PORT:-19200}"
  local os_metrics_port="${EVIDARA_OPENSEARCH_METRICS_PORT:-19600}"
  local pubsub_port="${EVIDARA_PUBSUB_HOST_PORT:-18681}"
  case "$mode" in
    lite)
      echo "status-all is only applicable to search/full app compose mode." >&2
      exit 1
      ;;
    search)
      (cd "$ROOT_DIR" && EVIDARA_POSTGRES_HOST_PORT="$postgres_port" EVIDARA_OPENSEARCH_HTTP_PORT="$os_http_port" EVIDARA_OPENSEARCH_METRICS_PORT="$os_metrics_port" EVIDARA_PUBSUB_HOST_PORT="$pubsub_port" docker compose -f docker-compose.yml -f docker-compose.local.yml --profile search --profile apps ps)
      ;;
    full)
      (cd "$ROOT_DIR" && EVIDARA_POSTGRES_HOST_PORT="$postgres_port" EVIDARA_OPENSEARCH_HTTP_PORT="$os_http_port" EVIDARA_OPENSEARCH_METRICS_PORT="$os_metrics_port" EVIDARA_PUBSUB_HOST_PORT="$pubsub_port" docker compose -f docker-compose.yml -f docker-compose.local.yml --profile full --profile apps ps)
      ;;
  esac
}

print_env() {
  local mode
  mode="$(normalize_mode "${1:-search}")"
  cat <<'EOF'
export OPENSEARCH_NODE="http://127.0.0.1:9200"
export PLATFORM_CONTROL_DATABASE_URL="postgresql+asyncpg://platform_control:platform_control@127.0.0.1:5432/platform_control"
export PUBSUB_EMULATOR_HOST="127.0.0.1:8681"
export PUBSUB_PROJECT_ID="evidara-local"
EOF
  if [[ "$mode" == "lite" ]]; then
    echo "# lite mode: OPENSEARCH_NODE and PUBSUB_* are optional/not required."
  elif [[ "$mode" == "search" ]]; then
    echo "# search mode: PUBSUB_* is optional."
  fi
}

check_all() {
  local mode
  mode="$(normalize_mode "${1:-search}")"
  if [[ "$mode" == "lite" ]]; then
    echo "check-all requires search or full mode (search API/frontend are required)." >&2
    exit 1
  fi

  echo "Checking local stack endpoints..."

  local pc_api
  local pc_admin
  local ls_api
  local ls_ui
  local ls_query

  check_endpoint() {
    local url="$1"
    local attempts="${2:-10}"
    local sleep_seconds="${3:-2}"
    local code="000"
    local i
    for ((i=1; i<=attempts; i++)); do
      code="$(curl --max-time 10 -sS -o /dev/null -w "%{http_code}" "$url" || true)"
      if [[ "$code" == "200" ]]; then
        echo "$code"
        return 0
      fi
      sleep "$sleep_seconds"
    done
    echo "$code"
    return 1
  }

  pc_api="$(check_endpoint "http://127.0.0.1:8000/health" 10 2)"
  pc_admin="$(check_endpoint "http://127.0.0.1:3100" 10 2)"
  ls_api="$(check_endpoint "http://127.0.0.1:3102/health" 10 2)"
  ls_ui="$(check_endpoint "http://127.0.0.1:3101" 10 2)"
  ls_query="$(check_endpoint "http://127.0.0.1:3102/v1/search?q=art%20754" 10 2)"

  echo "platform-control API /health: ${pc_api}"
  echo "platform-control admin /:     ${pc_admin}"
  echo "legal-search API /health:      ${ls_api}"
  echo "legal-search frontend /:       ${ls_ui}"
  echo "legal-search API /v1/search:   ${ls_query}"

  if [[ "$pc_api" != "200" || "$pc_admin" != "200" || "$ls_api" != "200" || "$ls_ui" != "200" || "$ls_query" != "200" ]]; then
    echo "One or more checks failed." >&2
    exit 1
  fi

  echo "All checks passed."
}

COMMAND="${1:-help}"
MODE="${2:-search}"
case "$COMMAND" in
  up)
    compose_up "$MODE"
    ;;
  up-all)
    compose_up_all "$MODE"
    ;;
  down)
    compose_down "$MODE"
    ;;
  down-all)
    compose_down_all "$MODE"
    ;;
  status)
    compose_status "$MODE"
    ;;
  status-all)
    compose_status_all "$MODE"
    ;;
  check-all)
    check_all "$MODE"
    ;;
  env)
    print_env "$MODE"
    ;;
  help|-h|--help)
    usage
    ;;
  *)
    echo "Unknown command: $COMMAND" >&2
    usage >&2
    exit 1
    ;;
esac
