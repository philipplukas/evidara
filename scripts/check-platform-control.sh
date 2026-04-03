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
    npm run build
  )
fi
