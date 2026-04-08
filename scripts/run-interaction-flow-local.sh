#!/usr/bin/env bash
# One-shot local run matching CI interaction-flow evidence (smoke + contract + screenshot pack).
# Starts Next dev servers via Playwright webServer unless PLAYWRIGHT_EXTERNAL_BASE_URL is set.
#
# Usage (repo root):
#   bash scripts/run-interaction-flow-local.sh
#   bash scripts/run-interaction-flow-local.sh --record   # full trace + video for every test (large artifacts)
#
# Env (optional):
#   PLAYWRIGHT_TRACE=on              — record every test (large artifacts; full journey replay)
#   PLAYWRIGHT_TRACE=off             — disable traces
#   PLAYWRIGHT_VIDEO=off             — disable failure videos
#   PLAYWRIGHT_EXTERNAL_BASE_URL=…   — staging/prod UI URL (skip local webServer)
#   PLAYWRIGHT_USE_REAL_BACKEND=true — point local UI at BFF (see playwright.config.ts)
set -euo pipefail
REPO_ROOT="$(cd "$(dirname "${BASH_SOURCE[0]}")/.." && pwd)"
FRONTEND="${REPO_ROOT}/legal-search/frontend"
ADMIN="${REPO_ROOT}/platform-control/admin"

if [[ "${1:-}" == "--record" ]]; then
  export PLAYWRIGHT_TRACE="on"
  export PLAYWRIGHT_VIDEO="on"
  shift
fi

export PLAYWRIGHT_TRACE="${PLAYWRIGHT_TRACE:-retain-on-failure}"

echo "Installing dependencies (frontend + admin for Playwright webServer)..." >&2
(cd "${FRONTEND}" && npm ci)
(cd "${ADMIN}" && npm ci)

echo "Installing Chromium for Playwright..." >&2
(cd "${FRONTEND}" && npx playwright install chromium)

if [[ "${PLAYWRIGHT_TRACE}" == "on" ]]; then
  echo "Running interaction-flow suites with FULL trace + video (PLAYWRIGHT_TRACE=on)..." >&2
  (cd "${FRONTEND}" && npm run e2e:interaction-flow:record)
else
  echo "Running interaction-flow suites (smoke → contract → screenshot pack)..." >&2
  (cd "${FRONTEND}" && npm run e2e:interaction-flow)
fi

echo "" >&2
echo "Done. HTML report: ${FRONTEND}/playwright-report/index.html" >&2
echo "Traces/videos (on failure, or trace=on): ${FRONTEND}/test-results/" >&2
