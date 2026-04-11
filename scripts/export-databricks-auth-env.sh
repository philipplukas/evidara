#!/usr/bin/env bash
# Emit shell exports for DATABRICKS_HOST / DATABRICKS_TOKEN (and related vars) from
# the Databricks CLI profile. Use: eval "$(scripts/export-databricks-auth-env.sh -p dev)"
#
# Prerequisite: databricks auth login (or OAuth) for that profile — see:
#   databricks auth login --help
set -euo pipefail

PROFILE="${DATABRICKS_CONFIG_PROFILE:-DEFAULT}"
usage() {
  cat <<'EOF'
Usage:
  eval "$(scripts/export-databricks-auth-env.sh -p <profile>)"

Options:
  -p, --profile NAME   Profile in ~/.databrickscfg (default: DEFAULT or DATABRICKS_CONFIG_PROFILE)
  -h, --help           Show this help
EOF
}

while [[ $# -gt 0 ]]; do
  case "$1" in
    -p|--profile) PROFILE="$2"; shift 2 ;;
    -h|--help) usage; exit 0 ;;
    *) echo "Unknown option: $1" >&2; usage >&2; exit 1 ;;
  esac
done

command -v databricks >/dev/null 2>&1 || {
  echo "ERROR: databricks CLI not found. Install: https://docs.databricks.com/dev-tools/cli/install.html" >&2
  exit 1
}

databricks auth env --profile "$PROFILE" --output json | python3 -c '
import json, shlex, sys

data = json.load(sys.stdin)
env = data.get("env") or {}
for key in sorted(env.keys()):
    val = env[key]
    if val is None or val == "":
        continue
    print(f"export {key}={shlex.quote(str(val))}")
'
