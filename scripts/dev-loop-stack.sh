#!/usr/bin/env bash
set -euo pipefail

# Bring up (and verify) the full acquisition -> search loop locally.
#
# WHY THIS EXISTS
# ---------------
# The loop stack has two settings that are inert by default and silent when
# wrong. `docker-compose.local.yml` defaults
# `PLATFORM_CONTROL_EVENT_PUBLISHER_BACKEND` to `noop` and
# `PLATFORM_CONTROL_ARTIFACT_STORE_BACKEND` to `local`, so a stack brought up
# without exporting them acquires documents perfectly and then never publishes
# the artifact event. document-intelligence has nothing to consume, logs
# nothing, and the run appears to hang at `canonical_ready=0` with no error
# anywhere. That cost a debugging cycle on 2026-07-20 (#735).
#
# The second trap is partial rebuilds. `platform-control-init` — which runs
# `alembic upgrade head` — is a separate image from `platform-control-api`.
# Rebuilding the API alone leaves migrations running from a stale image, and
# alembic then reports success while applying nothing, because as far as that
# image is concerned it *is* at head. A missing migration is invisible until a
# write hits a column or enum the code expects and the database has never heard
# of.
#
# Both traps share a shape: the stack is internally inconsistent and every
# individual component reports healthy. So this script does not merely set the
# variables — `verify` re-derives the invariants from the repo and fails loudly
# when the running stack disagrees. Prefer it over remembering the flags.
#
# RELATIONSHIP TO scripts/local-vertical-slice.sh
# -----------------------------------------------
# That script owns the lighter `lite`/`search`/`full` dependency modes and
# predates ADR-0029, so it brings up neither NATS nor MinIO and does not
# configure the event path. Use it for API/search work against plain
# dependencies; use this one when the loop itself has to run end to end.

ROOT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")/.." && pwd)"

# The non-inert values. Exported for every compose invocation below so a
# rebuild, a restart of one service, and a full bring-up all agree.
export PLATFORM_CONTROL_EVENT_PUBLISHER_BACKEND="${PLATFORM_CONTROL_EVENT_PUBLISHER_BACKEND:-nats}"
export PLATFORM_CONTROL_ARTIFACT_STORE_BACKEND="${PLATFORM_CONTROL_ARTIFACT_STORE_BACKEND:-s3}"

COMPOSE_FILES=(-f docker-compose.yml -f docker-compose.local.yml)
# `search` is required alongside `apps`: opensearch lives behind the search
# profile and legal-search-api depends on it, so apps+nats+minio alone fails
# compose config validation.
COMPOSE_PROFILES=(--profile apps --profile search --profile nats --profile minio)

usage() {
  cat <<'EOF'
Usage: bash scripts/dev-loop-stack.sh <command>

Commands:
  up        Rebuild every image, bring the stack up, then verify
  verify    Check a running stack for the inconsistencies that fail silently
  down      Stop the stack and REMOVE VOLUMES (fresh database next time)
  restart <service>
            Rebuild and restart one service, keeping the event-path env
  help      Show this message

Env overrides (defaults are the working values, not compose's inert ones):
  PLATFORM_CONTROL_EVENT_PUBLISHER_BACKEND  default nats
  PLATFORM_CONTROL_ARTIFACT_STORE_BACKEND   default s3
EOF
}

compose() {
  (cd "$ROOT_DIR" && docker compose "${COMPOSE_FILES[@]}" "${COMPOSE_PROFILES[@]}" "$@")
}

log() { printf '%s\n' "$*" >&2; }

# First argument is the headline; any further arguments are indented detail
# lines. Kept as separate arguments rather than one concatenated string —
# adjacent quoted strings across line continuations are a shell foot-gun
# (SC2140) that silently mangles the message.
fail() {
  printf 'FAIL: %s\n' "$1" >&2
  shift
  local line
  for line in "$@"; do
    printf '      %s\n' "${line}" >&2
  done
  return 1
}

# The newest migration in the repo, by filename. Alembic revisions here are
# date-prefixed (20260720_0023), so lexical order is chronological order.
expected_alembic_head() {
  local newest
  newest="$(find "${ROOT_DIR}/platform-control/alembic/versions" -name '*.py' -printf '%f\n' \
    | sort | tail -1)"
  # 20260720_0023_run_mode_acceptance.py -> 20260720_0023
  printf '%s' "${newest}" | sed -E 's/^([0-9]{8}_[0-9]{4}).*/\1/'
}

verify() {
  local failures=0

  log "==> Verifying the running stack against the repo"

  # 1. The event path. `noop` is the failure that presents as a hang.
  local publisher store
  publisher="$(docker exec evidara-platform-control-api-1 \
    printenv PLATFORM_CONTROL_EVENT_PUBLISHER_BACKEND 2>/dev/null || printf 'unset')"
  store="$(docker exec evidara-platform-control-api-1 \
    printenv PLATFORM_CONTROL_ARTIFACT_STORE_BACKEND 2>/dev/null || printf 'unset')"
  if [[ "${publisher}" == "noop" || "${publisher}" == "unset" ]]; then
    fail "event publisher is '${publisher}': artifact events are never published." \
      "document-intelligence will sit idle, runs appear to hang at canonical_ready=0," \
      "and nothing logs an error. Fix: bash scripts/dev-loop-stack.sh up" || failures=1
  else
    log "    event publisher = ${publisher}"
  fi
  if [[ "${store}" == "unset" ]]; then
    fail "artifact store backend is unset" || failures=1
  else
    log "    artifact store   = ${store}"
  fi

  # 2. The dispatch path. RunService._should_dispatch_via_worker() forces worker
  #    dispatch for _ASYNC_PROVIDER_NAMES (currently `ris_ogd`) whatever
  #    PLATFORM_CONTROL_RUN_DISPATCH_BACKEND says, so without this container an
  #    AT RIS run sits PENDING forever with refused=false and no failure_reason.
  #    Same class of silent failure as the publisher above: nothing errors.
  local worker_publisher
  if ! docker inspect evidara-platform-control-worker-1 >/dev/null 2>&1; then
    fail "platform-control-worker is not running: runs for async providers" \
      "(ris_ogd) will stay PENDING and never dispatch, with no error anywhere." \
      "Fix: bash scripts/dev-loop-stack.sh up" || failures=1
  else
    # Parity, not just presence. A worker on `noop`/`local` completes the run
    # and publishes nothing the DI consumer can read — the 2026-04-14 AT RIS
    # break, which cost a live debugging cycle on dev.
    worker_publisher="$(docker exec evidara-platform-control-worker-1 \
      printenv PLATFORM_CONTROL_EVENT_PUBLISHER_BACKEND 2>/dev/null || printf 'unset')"
    if [[ "${worker_publisher}" != "${publisher}" ]]; then
      fail "worker event publisher is '${worker_publisher}' but the API's is" \
        "'${publisher}'. The worker owns acquisition dispatch, so its backends —" \
        "not the API's — decide whether anything reaches document-intelligence." \
        "Fix: bash scripts/dev-loop-stack.sh up" || failures=1
    else
      log "    worker publisher = ${worker_publisher} (matches API)"
    fi
  fi

  # 3. Migrations. A stale platform-control-init image reports success while
  #    applying nothing, so compare the database against the repo rather than
  #    trusting the init container's exit code.
  local expected actual
  expected="$(expected_alembic_head)"
  # shellcheck disable=SC2016 # $POSTGRES_USER/$POSTGRES_DB expand inside the container
  actual="$(compose exec -T postgres sh -c \
    'psql -U "$POSTGRES_USER" -d "$POSTGRES_DB" -tAc "SELECT version_num FROM alembic_version"' \
    2>/dev/null | tr -d '[:space:]' || true)"
  if [[ "${actual}" != "${expected}" ]]; then
    fail "alembic head is '${actual}' but the repo's newest migration is '${expected}'." \
      "The platform-control-init image is probably stale — it runs migrations from its" \
      "own build, so rebuilding platform-control-api alone is not enough." \
      "Fix: bash scripts/dev-loop-stack.sh up" || failures=1
  else
    log "    alembic head     = ${actual}"
  fi

  # 4. Health. Last, because the two above are true even when everything is
  #    reporting healthy — that is the whole point.
  local name url code
  for pair in "platform-control=http://localhost:8000/health" \
              "legal-search=http://localhost:3102/health" \
              "admin=http://localhost:3100"; do
    name="${pair%%=*}"
    url="${pair#*=}"
    code="$(curl -s -o /dev/null -w '%{http_code}' --max-time 10 "${url}" || printf '000')"
    if [[ "${code}" != "200" ]]; then
      fail "${name} returned HTTP ${code} (${url})" || failures=1
    else
      log "    ${name} = 200"
    fi
  done

  if [[ "${failures}" -ne 0 ]]; then
    log "==> Stack is INCONSISTENT. See failures above."
    return 1
  fi
  log "==> Stack is consistent with the repo."
}

case "${1:-help}" in
  up)
    # Build everything. Naming services here is what produces the stale-init
    # trap, so this deliberately takes no service argument.
    log "==> Building every image"
    compose build
    log "==> Starting the stack"
    compose up -d --wait
    verify
    ;;
  verify)
    verify
    ;;
  down)
    log "==> Stopping the stack and removing volumes"
    compose down -v --remove-orphans
    ;;
  restart)
    service="${2:?usage: dev-loop-stack.sh restart <service>}"
    log "==> Rebuilding and restarting ${service}"
    compose build "${service}"
    compose up -d --wait --force-recreate "${service}"
    # Verify anyway: restarting one service is exactly when the stack drifts out
    # of agreement with itself.
    verify
    ;;
  help|-h|--help)
    usage
    ;;
  *)
    printf 'Unknown command: %s\n\n' "$1" >&2
    usage >&2
    exit 1
    ;;
esac
