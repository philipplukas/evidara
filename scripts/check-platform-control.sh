#!/usr/bin/env bash
set -euo pipefail

cd platform-control

uv run ruff check .
uv run ruff format --check .
uv run pytest

if [[ -f admin/package.json ]]; then
  (
    cd admin
    npm run check
    PLATFORM_CONTROL_API_URL="${PLATFORM_CONTROL_API_URL:-http://127.0.0.1:8000}" npm run build
  )
fi
