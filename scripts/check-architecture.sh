#!/usr/bin/env bash
set -euo pipefail

# Validate Structurizr workspace DSL
# Requires: Docker (structurizr/cli) or structurizr-cli installed locally

if [ ! -f structurizr/workspace.dsl ]; then
  echo "No structurizr/workspace.dsl found — skipping"
  exit 0
fi

# Try local CLI first, fall back to Docker
if command -v structurizr >/dev/null 2>&1; then
  echo "Validating Structurizr DSL (local CLI)..."
  structurizr validate -workspace structurizr/workspace.dsl
elif command -v docker >/dev/null 2>&1; then
  echo "Validating Structurizr DSL (Docker)..."
  docker run --rm \
    -v "$(pwd)/structurizr:/usr/local/structurizr" \
    structurizr/cli \
    validate -workspace /usr/local/structurizr/workspace.dsl
else
  echo "Warning: neither structurizr CLI nor Docker available — skipping DSL validation"
  echo "Install Docker to enable: docker run structurizr/cli validate ..."
  exit 0
fi

echo "Structurizr DSL is valid."
