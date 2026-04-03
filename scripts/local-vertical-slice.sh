#!/usr/bin/env bash
set -euo pipefail

ROOT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")/.." && pwd)"

usage() {
  cat <<'EOF'
Usage: bash scripts/local-vertical-slice.sh <command>

Commands:
  up        Start local runtime dependencies (postgres, opensearch, pubsub emulator)
  down      Stop local runtime dependencies
  status    Show dependency container status
  env       Print local env variables used by runtime services
  help      Show this message
EOF
}

compose_up() {
  (cd "$ROOT_DIR" && docker compose up -d postgres opensearch pubsub)
}

compose_down() {
  (cd "$ROOT_DIR" && docker compose stop postgres opensearch pubsub)
}

compose_status() {
  (cd "$ROOT_DIR" && docker compose ps postgres opensearch pubsub)
}

print_env() {
  cat <<'EOF'
export OPENSEARCH_NODE="http://127.0.0.1:9200"
export PLATFORM_CONTROL_DATABASE_URL="postgresql+asyncpg://platform_control:platform_control@127.0.0.1:5432/platform_control"
export PUBSUB_EMULATOR_HOST="127.0.0.1:8681"
export PUBSUB_PROJECT_ID="evidara-local"
EOF
}

COMMAND="${1:-help}"
case "$COMMAND" in
  up)
    compose_up
    ;;
  down)
    compose_down
    ;;
  status)
    compose_status
    ;;
  env)
    print_env
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
