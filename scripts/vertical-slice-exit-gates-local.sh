#!/usr/bin/env bash
# Local checks from docs/runbooks/first-vertical-slice-exit-gates.md (Local Verification Commands).
# Use before claiming dev/staging runtime gate evidence; does not replace scripts/e2e-smoke-test.sh.
set -euo pipefail

ROOT="$(cd "$(dirname "${BASH_SOURCE[0]}")/.." && pwd)"
cd "$ROOT"

echo "==> legal-search: projections.service.spec.ts"
(cd legal-search/api && npm test -- --run src/modules/projections/projections.service.spec.ts)

echo "==> platform-control: firecrawl webhook unit tests"
(cd platform-control && uv run pytest tests/unit/test_firecrawl_webhook_service.py -q)

echo "vertical-slice-exit-gates-local: OK"
