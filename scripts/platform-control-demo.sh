#!/usr/bin/env bash
set -euo pipefail

ROOT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")/.." && pwd)"
PLATFORM_CONTROL_DIR="${ROOT_DIR}/platform-control"
PLATFORM_CONTROL_ADMIN_DIR="${PLATFORM_CONTROL_DIR}/admin"
DEFAULT_DATABASE_URL="postgresql+asyncpg://platform_control:platform_control@127.0.0.1:5432/platform_control"

export PLATFORM_CONTROL_DATABASE_URL="${PLATFORM_CONTROL_DATABASE_URL:-$DEFAULT_DATABASE_URL}"
# Settings.environment is required and has no default (#683). This script is the local
# demo, so it declares "development" explicitly rather than relying on a default that
# would also have been what production silently reported.
export PLATFORM_CONTROL_ENVIRONMENT="${PLATFORM_CONTROL_ENVIRONMENT:-development}"

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
  seed-demo-runs
                Seed one run per lifecycle state (pending / running / completed /
                failed / cancelled) so the admin run queue has something to triage.
                LOCAL ONLY - refuses unless PLATFORM_CONTROL_ENVIRONMENT=development.
  bootstrap     Run up + sync + migrate + seed
  dev           The inner dev loop: Postgres + API + admin, all with reload.
                Admin on :3000, API on :8000. Ctrl-C stops both. Use this for
                writing code; use docker-compose.local.yml --profile apps for
                acceptance runs and e2e (see docs/setup/local-dev-loops.md).
  api           Start the platform-control API with reload
  admin         Start the platform-control/admin app
  health        Call the local /health endpoint
  help          Show this message

Environment:
  PLATFORM_CONTROL_DATABASE_URL
      Defaults to:
      postgresql+asyncpg://platform_control:platform_control@127.0.0.1:5432/platform_control
  PLATFORM_CONTROL_ENVIRONMENT
      development | staging | production. Required by the app (no default); this
      script exports "development" unless you set it.
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

wait_for_postgres() {
  require_cmd docker
  echo "Waiting for Postgres to be ready..."
  local retries=30
  while ! (cd "$ROOT_DIR" && docker compose exec -T postgres pg_isready -U platform_control -d platform_control >/dev/null 2>&1); do
    retries=$((retries - 1))
    if [ "$retries" -eq 0 ]; then
      echo "Postgres did not become ready in time." >&2
      exit 1
    fi
    sleep 1
  done
  echo "Postgres is ready."
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

# Runs acquired by the local acceptance loop are all `completed`, so the admin's
# triage affordances (attention chip, cancel action, failure copy, the five
# preset chips) had no rows to render and could not be reviewed locally. This
# writes one fixture run per lifecycle state. The seeder refuses outside
# PLATFORM_CONTROL_ENVIRONMENT=development, which this script exports as
# "development" by default.
seed_demo_runs() {
  require_cmd uv
  run_in_platform_control uv run platform-control-seed-demo-runs \
    --i-know-this-writes-fake-runs
}

# Auth fails closed: with no API key configured, EVERY protected route answers
# 503 and the admin renders empty lists - which reads as a data bug, not a config
# one. `docker-compose.local.yml` already opts the local stack into the keyless
# path by name; this script did not, so the two local paths disagreed and only
# the compose one worked. LOCAL ONLY - never set in a deployment.
start_api() {
  require_cmd uv
  export PLATFORM_CONTROL_AUTH_DEV_ALLOW_UNAUTHENTICATED="${PLATFORM_CONTROL_AUTH_DEV_ALLOW_UNAUTHENTICATED:-1}"
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

# The inner dev loop in one command: Postgres in Docker, API and admin on the
# host with reload. Three terminals in the right order was the previous answer,
# and the order matters - the admin's BFF proxies to :8000, so an admin started
# first serves a wall of connection errors that look like real failures.
#
# This is deliberately NOT `docker-compose.local.yml --profile apps`: that stack
# builds both services from Dockerfiles with no source mounts and no --reload, so
# every edit costs a rebuild. It is the integration stack (NATS, MinIO,
# OpenSearch, worker, projection bridge) and stays the right tool for acceptance
# runs and e2e. See docs/setup/local-dev-loops.md.
start_dev() {
  require_cmd uv
  require_cmd npm
  # setsid puts each child in its own process group so the trap can signal the
  # WHOLE tree. Without it, `uv run uvicorn` and `npm run dev` leave orphaned
  # grandchildren still holding :8000 and :3000 after Ctrl-C, and the next `dev`
  # fails with "address already in use" for reasons nothing on screen explains.
  require_cmd setsid
  local api_pid="" admin_pid=""

  stop_dev() {
    echo
    echo "Stopping dev stack..."
    # Negative PID signals the process GROUP. setsid made each child a group
    # leader, so its PID doubles as its PGID.
    [ -n "$admin_pid" ] && kill -TERM -- "-$admin_pid" 2>/dev/null || true
    [ -n "$api_pid" ] && kill -TERM -- "-$api_pid" 2>/dev/null || true
    wait 2>/dev/null || true
  }
  trap stop_dev INT TERM EXIT

  compose_up
  wait_for_postgres

  setsid bash "$0" api > >(sed -u 's/^/[api]   /') 2>&1 &
  api_pid=$!

  echo "Waiting for the API on :8000..."
  for _ in $(seq 1 40); do
    if curl -fsS -m 2 http://127.0.0.1:8000/health >/dev/null 2>&1; then break; fi
    sleep 1
  done
  if ! curl -fsS -m 2 http://127.0.0.1:8000/health >/dev/null 2>&1; then
    echo "API did not become healthy on :8000 - see the [api] lines above." >&2
    return 1
  fi
  echo "API is healthy."

  setsid bash "$0" admin > >(sed -u 's/^/[admin] /') 2>&1 &
  admin_pid=$!

  cat <<'BANNER'

  Dev loop is up. Edits reload automatically - no rebuild, no deploy.
    admin  http://localhost:3000     (HMR; compose serves its own build on :3100)
    api    http://127.0.0.1:8000     (uvicorn --reload)

  Ctrl-C stops both.

BANNER
  wait
}

bootstrap() {
  compose_up
  wait_for_postgres
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
  seed-demo-runs)
    seed_demo_runs
    ;;
  bootstrap)
    bootstrap
    ;;
  dev)
    start_dev
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
