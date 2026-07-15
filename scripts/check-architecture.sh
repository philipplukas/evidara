#!/usr/bin/env bash
set -euo pipefail

# Validate the Structurizr workspace DSL — the declared source of truth for system
# architecture (see AGENTS.md).
#
# This is a *parser*, not a fact-checker. It fails on malformed DSL: bad syntax, an
# unclosed block, a relationship or view referencing an identifier that was never
# defined. It cannot tell you the model has drifted from reality.
#
# Requires: Docker, or a local structurizr CLI.
#
# NOTE ON THE IMAGE: this uses `structurizr/structurizr`, NOT the older
# `structurizr/cli`. `structurizr/cli` is now a deprecation stub — it prints a
# "please migrate" banner and exits 0 *without validating anything*, so a script
# built on it reports success on a DSL that does not even parse. Do not switch back.
#
# Usage:
#   bash scripts/check-architecture.sh            # skip if no validator (local dev)
#   bash scripts/check-architecture.sh --strict   # fail if no validator (CI)
#
# --strict exists because skipping on a missing validator makes a silent no-op look
# identical to a pass. CI must not grade itself on a check it never ran.

STRICT=0
if [[ "${1:-}" == "--strict" ]]; then
  STRICT=1
fi

WORKSPACE="structurizr/workspace.dsl"
IMAGE="structurizr/structurizr"

die_or_skip() {
  local message="$1"
  if [[ "$STRICT" -eq 1 ]]; then
    echo "ERROR: ${message}." >&2
    echo "Refusing to report success in --strict mode without validating the DSL." >&2
    exit 1
  fi
  echo "Warning: ${message} — skipping DSL validation."
  echo "Install Docker to run it locally; CI runs this with --strict."
  exit 0
}

if [ ! -f "$WORKSPACE" ]; then
  die_or_skip "no ${WORKSPACE} found"
fi

if command -v structurizr >/dev/null 2>&1; then
  echo "Validating Structurizr DSL (local CLI)..."
  structurizr validate -workspace "$WORKSPACE"
elif command -v docker >/dev/null 2>&1 && docker info >/dev/null 2>&1; then
  echo "Validating Structurizr DSL (Docker: ${IMAGE})..."
  docker run --rm \
    -v "$(pwd)/structurizr:/work" \
    -w /work \
    "$IMAGE" \
    validate -workspace "$(basename "$WORKSPACE")"
else
  die_or_skip "neither the structurizr CLI nor a reachable Docker daemon is available"
fi

echo "Structurizr DSL is valid."
