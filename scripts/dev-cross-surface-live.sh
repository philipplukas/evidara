#!/usr/bin/env bash
set -euo pipefail

ROOT="$(cd "$(dirname "${BASH_SOURCE[0]}")/.." && pwd)"
FRONTEND_PORT="${EVIDARA_LEGAL_SEARCH_FRONTEND_PORT:-3101}"
ADMIN_PORT="${EVIDARA_CONTROL_PANEL_PORT:-3100}"
API_URL="${EVIDARA_LEGAL_SEARCH_API_URL:-http://localhost:3102}"
FRONTEND_URL="http://localhost:${FRONTEND_PORT}"
ADMIN_URL="http://localhost:${ADMIN_PORT}"

frontend_pid=""
admin_pid=""

require_cmd() {
  local name="$1"
  local hint="$2"
  if ! command -v "$name" >/dev/null 2>&1; then
    echo "error: missing required command '$name'" >&2
    echo "hint: $hint" >&2
    exit 1
  fi
}

cleanup() {
  local status=$?

  if [[ -n "$frontend_pid" ]] && kill -0 "$frontend_pid" 2>/dev/null; then
    kill "$frontend_pid" 2>/dev/null || true
  fi
  if [[ -n "$admin_pid" ]] && kill -0 "$admin_pid" 2>/dev/null; then
    kill "$admin_pid" 2>/dev/null || true
  fi

  wait "$frontend_pid" 2>/dev/null || true
  wait "$admin_pid" 2>/dev/null || true

  "$ROOT/scripts/dev-lean-search-stack.sh" down >/dev/null 2>&1 || true
  exit "$status"
}

trap cleanup EXIT INT TERM

require_cmd docker "Install Docker as part of the MacConfig workstation baseline, then rerun this launcher."
require_cmd npm "Install Node.js/npm, then rerun this launcher."

echo "Starting lean backend stack..."
"$ROOT/scripts/dev-lean-search-stack.sh" up

echo "Starting legal-search frontend on ${FRONTEND_URL}..."
(
  cd "$ROOT/legal-search/frontend"
  NEXT_PUBLIC_API_URL="$API_URL" \
  NEXT_PUBLIC_CONTROL_PANEL_URL="$ADMIN_URL" \
  NEXT_PUBLIC_DEFAULT_UI_PROFILE="admin" \
  npm run dev -- --port "$FRONTEND_PORT"
) &
frontend_pid=$!

echo "Starting control-panel admin on ${ADMIN_URL}..."
(
  cd "$ROOT/platform-control/admin"
  NEXT_PUBLIC_USER_ROLE="admin" \
  NEXT_PUBLIC_ADMIN_ALLOWED_ROLES="admin" \
  NEXT_PUBLIC_LEGAL_SEARCH_URL="$FRONTEND_URL" \
  npm run dev -- --port "$ADMIN_PORT"
) &
admin_pid=$!

echo "Waiting for local cross-surface preflight..."
EVIDARA_LEGAL_SEARCH_FRONTEND_URL="$FRONTEND_URL" \
EVIDARA_CONTROL_PANEL_URL="$ADMIN_URL" \
EVIDARA_LEGAL_SEARCH_API_URL="$API_URL" \
"$ROOT/scripts/preflight-cross-surface-live.sh" --wait --timeout 90

cat <<EOF
Cross-surface live workflow is ready.

Frontend: ${FRONTEND_URL}
Admin:    ${ADMIN_URL}
API:      ${API_URL}

Suggested next steps:
  - mocked UI work: cd legal-search/frontend && npm run test
  - live round-trip validation: cd legal-search/frontend && PLAYWRIGHT_USE_REAL_BACKEND=true npm run e2e:contract

Press Ctrl-C to stop the frontend, admin, and lean backend stack.
EOF

wait "$frontend_pid" "$admin_pid"
