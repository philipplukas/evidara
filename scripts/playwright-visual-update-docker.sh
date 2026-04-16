#!/usr/bin/env bash
# Regenerate Playwright *-linux.png baselines using the official Playwright image (matches CI OS).
# Bump the image tag when bumping @playwright/test in legal-search/frontend/package.json.
set -euo pipefail
ROOT="$(cd "$(dirname "${BASH_SOURCE[0]}")/.." && pwd)"
IMAGE="${PLAYWRIGHT_DOCKER_IMAGE:-mcr.microsoft.com/playwright:v1.59.1-jammy}"

docker run --rm \
  -v "${ROOT}:/work" \
  -w /work/legal-search/frontend \
  "${IMAGE}" \
  bash -lc "npm ci && npx playwright install --with-deps chromium && npm run e2e:visual:update"

echo "Commit updated files under legal-search/frontend/e2e/visual.spec.ts-snapshots/ (expect *-linux.png on Linux)."
