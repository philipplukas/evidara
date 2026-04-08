#!/usr/bin/env bash
# Optional smoke: platform-control + legal-search via evidara-cli.
# Requires both APIs reachable at EVIDARA_* URLs (see tools/evidara-cli/README.md).
# Default: no-op exit 0 unless EVIDARA_CLI_SMOKE=1.
set -euo pipefail
REPO_ROOT="$(cd "$(dirname "${BASH_SOURCE[0]}")/.." && pwd)"

if [[ "${EVIDARA_CLI_SMOKE:-}" != "1" ]]; then
  echo "Skipping evidara-cli smoke (set EVIDARA_CLI_SMOKE=1 to run)." >&2
  exit 0
fi

cd "$REPO_ROOT/tools/evidara-cli"
uv sync --group dev --quiet
uv run evidara platform-control ping
uv run evidara legal-search ping
echo "evidara-cli smoke: OK" >&2
