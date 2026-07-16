#!/usr/bin/env bash
set -euo pipefail

cd platform-control

uv run ruff check .
uv run ruff format --check .
uv run pytest

# contracts/api/platform-control.openapi.yaml is generated from this app, not
# hand-maintained (#618). Without this gate the contract drifts behind the models
# and consumers that trust it ship bugs — #614 (admin knew 4 of 11 acquisition
# providers and coerced the rest to firecrawl) and #616 (contract omitted the list
# pagination envelope, so the admin capped every list at 100). Mirrors
# legal-search/frontend's `npm run openapi:check`.
uv run python ../scripts/generate_platform_control_contract.py --check

if [[ -f admin/package.json ]]; then
  (
    cd admin
    npm run check
    PLATFORM_CONTROL_API_URL="${PLATFORM_CONTROL_API_URL:-http://127.0.0.1:8000}" npm run build
  )
fi
