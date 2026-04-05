#!/usr/bin/env bash
set -euo pipefail

# Scraping/acquisition-focused QA gate for platform-control.
# Keep this suite small and deterministic for PR-time enforcement.

echo "==> Validate shared contracts/examples"
uv run --project platform-control python scripts/validate_json_schemas.py

echo "==> Run scraping/acquisition unit tests"
(
  cd platform-control
  uv run pytest -q \
    tests/unit/test_artifact_bundle.py \
    tests/unit/test_artifact_bundle_contracts.py \
    tests/unit/test_firecrawl_provider.py \
    tests/unit/test_firecrawl_webhook_service.py
)
