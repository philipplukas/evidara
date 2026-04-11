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

# Machine-readable hint for CI / TAR-67 drill logs (attach alongside workflow run URL in Linear).
export RUN_URL=""
if [[ -n "${GITHUB_SERVER_URL:-}" && -n "${GITHUB_REPOSITORY:-}" && -n "${GITHUB_RUN_ID:-}" ]]; then
  export RUN_URL="${GITHUB_SERVER_URL}/${GITHUB_REPOSITORY}/actions/runs/${GITHUB_RUN_ID}"
fi
python3 -c "import json, os; print(json.dumps({'evidara_cli_smoke': 'ok', 'workflow_run_url': os.environ.get('RUN_URL') or None}))" >&2
echo "TAR-67: attach evidara-cli stdout + workflow run URL to Linear (see docs/runbooks/tar64-tar85-evidence-capture.md)." >&2
