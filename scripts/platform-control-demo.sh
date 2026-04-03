#!/usr/bin/env bash
set -euo pipefail

ROOT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")/.." && pwd)"
PLATFORM_CONTROL_DIR="${ROOT_DIR}/platform-control"
PLATFORM_CONTROL_ADMIN_DIR="${PLATFORM_CONTROL_DIR}/admin"
DEFAULT_DATABASE_URL="postgresql+asyncpg://platform_control:platform_control@127.0.0.1:5432/platform_control"

export PLATFORM_CONTROL_DATABASE_URL="${PLATFORM_CONTROL_DATABASE_URL:-$DEFAULT_DATABASE_URL}"

usage() {
  cat <<'EOF'
Usage: bash scripts/platform-control-demo.sh <command>

Commands:
  up            Start local Postgres for platform-control
  down          Stop local Postgres for platform-control
  status        Show local Postgres container status
  sync          Install platform-control dependencies with uv
  admin-sync    Install platform-control/admin dependencies with npm
  migrate       Run Alembic migrations against local Postgres
  seed          Seed reference data into local Postgres
  seed-dry-run  Validate and preview reference data changes
  bootstrap     Run up + sync + migrate + seed
  api           Start the platform-control API with reload
  admin         Start the platform-control/admin app
  health        Call the local /health endpoint
  help          Show this message

Environment:
  PLATFORM_CONTROL_DATABASE_URL
      Defaults to:
      postgresql+asyncpg://platform_control:platform_control@127.0.0.1:5432/platform_control
EOF
}

require_cmd() {
  if ! command -v "$1" >/dev/null 2>&1; then
    echo "Missing required command: $1" >&2
    exit 1
  fi
}

run_in_platform_control() {
  (
    cd "$PLATFORM_CONTROL_DIR"
    "$@"
  )
}

run_in_platform_control_admin() {
  (
    cd "$PLATFORM_CONTROL_ADMIN_DIR"
    "$@"
  )
}

compose_up() {
  require_cmd docker
  (cd "$ROOT_DIR" && docker compose up -d postgres)
}

compose_down() {
  require_cmd docker
  (cd "$ROOT_DIR" && docker compose stop postgres)
}

compose_status() {
  require_cmd docker
  (cd "$ROOT_DIR" && docker compose ps postgres)
}

sync_deps() {
  require_cmd uv
  run_in_platform_control uv sync --group dev
}

sync_admin_deps() {
  require_cmd npm
  run_in_platform_control_admin npm ci
}

migrate_db() {
  require_cmd uv
  run_in_platform_control uv run alembic upgrade head
}

seed_reference_data() {
  require_cmd uv
  run_in_platform_control uv run platform-control-seed-reference-data
}

seed_reference_data_dry_run() {
  require_cmd uv
  run_in_platform_control uv run platform-control-seed-reference-data --dry-run
}

start_api() {
  require_cmd uv
  run_in_platform_control uv run uvicorn platform_control.main:app --reload --app-dir src
}

start_admin() {
  require_cmd npm
  run_in_platform_control_admin npm run dev
}

check_health() {
  require_cmd curl
  curl -fsS http://127.0.0.1:8000/health
  echo
}

bootstrap() {
  compose_up
  sync_deps
  migrate_db
  seed_reference_data
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
  sync)
    sync_deps
    ;;
  admin-sync)
    sync_admin_deps
    ;;
  migrate)
    migrate_db
    ;;
  seed)
    seed_reference_data
    ;;
  seed-dry-run)
    seed_reference_data_dry_run
    ;;
  bootstrap)
    bootstrap
    ;;
  api)
    start_api
    ;;
  admin)
    start_admin
    ;;
  health)
    check_health
    ;;
  help|-h|--help)
    usage
    ;;
  *)
    echo "Unknown command: $COMMAND" >&2
    echo >&2
    usage >&2
    exit 1
    ;;
esac
