#!/usr/bin/env bash
# Regenerate Playwright *-linux.png baselines in the official Playwright image.
#
# WHAT THIS DOES AND DOES NOT MATCH (the header used to claim "matches CI OS";
# it did not, and the drift was never checked):
#
#   this image  mcr.microsoft.com/playwright:v1.59.1-jammy -> Ubuntu 22.04, Node 24
#   CI job      frontend-visual-regression -> ubuntu-latest (24.04) + setup-node@v5 Node 22
#
# So it matches CI on neither OS nor Node. It is still the most reproducible
# renderer available locally (a pinned Chromium + a pinned font stack, which is
# what actually drives pixel output), so it stays — but the claim is now stated
# honestly rather than asserted falsely.
#
# Deliberately NOT fixed here: switching to the `-noble` image would align the
# OS with ubuntu-latest, but noble/jammy differ in fontconfig and freetype, so
# the switch would rewrite every committed `-linux.png`. Baselines and VRT
# tolerances are owned by #611; this lane does not touch them. The Node-24
# divergence (repo `engines` are ">=22 <24") affects the dev server, not
# Chromium's rasterisation, and is checked below rather than silently ignored.
#
# Bump the image tag when bumping @playwright/test in legal-search/frontend/package.json.
set -euo pipefail
ROOT="$(cd "$(dirname "${BASH_SOURCE[0]}")/.." && pwd)"
IMAGE="${PLAYWRIGHT_DOCKER_IMAGE:-mcr.microsoft.com/playwright:v1.59.1-jammy}"

# Run as the invoking user. As root, the container wrote root-owned
# `test-results/` and `playwright-report/` into the worktree, and the next
# LOCAL Playwright run then died with EACCES — a container detail surfacing as
# an unrelated-looking test failure.
docker run --rm \
  --user "$(id -u):$(id -g)" \
  -e HOME=/tmp \
  -e npm_config_cache=/tmp/.npm \
  -v "${ROOT}:/work" \
  -w /work/legal-search/frontend \
  "${IMAGE}" \
  bash -lc '
    set -euo pipefail
    node_major="$(node -v | tr -d v | cut -d. -f1)"
    if [ "$node_major" != "22" ]; then
      echo "NOTE: container Node v${node_major}; CI (frontend-visual-regression) runs Node 22." >&2
      echo "      Baselines are rendered by Chromium, not Node, so this does not affect pixels," >&2
      echo "      but do not treat a green run here as a Node-parity signal." >&2
    fi
    cd /work/platform-control/admin && npm ci
    cd /work/legal-search/frontend && npm ci
    # Browsers and their system deps ship preinstalled in this image; installing
    # with --with-deps needs apt and would fail now that we are not root.
    npm run e2e:visual:update
  '

echo "Commit updated files under legal-search/frontend/e2e/visual.spec.ts-snapshots/ (expect *-linux.png on Linux)."
