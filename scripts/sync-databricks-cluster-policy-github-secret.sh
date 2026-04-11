#!/usr/bin/env bash
# Read the Evidara compute guardrails cluster policy id from the workspace using
# the Databricks CLI, then push it to a GitHub Actions environment secret (gh CLI).
#
# Prerequisite: gh auth login, databricks auth login for the profile, and the
# policy must exist (Terraform document_intelligence_stack with guardrails enabled).
set -euo pipefail

POLICY_NAME="Evidara compute guardrails"
REPO=""
GITHUB_ENV_NAME=""
PROFILE=""
APPLY="false"

usage() {
  cat <<'EOF'
Usage:
  scripts/sync-databricks-cluster-policy-github-secret.sh --env <dev|staging|prod> --profile <name> [options]

Required:
  --env NAME           GitHub Actions environment name (dev, staging, prod)
  --profile NAME       Databricks CLI profile (~/.databrickscfg) for that workspace

Options:
  --repo OWNER/NAME    Default: current repo from gh repo view
  --policy-name TEXT   Default: Evidara compute guardrails
  --apply              Actually run gh secret set (default is dry-run)
  -h, --help

Examples:
  scripts/sync-databricks-cluster-policy-github-secret.sh --env dev --profile dev
  scripts/sync-databricks-cluster-policy-github-secret.sh --env dev --profile dev --apply
EOF
}

while [[ $# -gt 0 ]]; do
  case "$1" in
    --repo) REPO="$2"; shift 2 ;;
    --env) GITHUB_ENV_NAME="$2"; shift 2 ;;
    --profile) PROFILE="$2"; shift 2 ;;
    --policy-name) POLICY_NAME="$2"; shift 2 ;;
    --apply) APPLY="true"; shift ;;
    -h|--help) usage; exit 0 ;;
    *) echo "Unknown option: $1" >&2; usage >&2; exit 1 ;;
  esac
done

[[ -n "$GITHUB_ENV_NAME" ]] || { echo "ERROR: --env is required" >&2; usage >&2; exit 1; }
[[ -n "$PROFILE" ]] || { echo "ERROR: --profile is required" >&2; usage >&2; exit 1; }

command -v gh >/dev/null 2>&1 || {
  echo "ERROR: gh CLI not found." >&2
  exit 1
}
command -v databricks >/dev/null 2>&1 || {
  echo "ERROR: databricks CLI not found." >&2
  exit 1
}
command -v python3 >/dev/null 2>&1 || {
  echo "ERROR: python3 required." >&2
  exit 1
}

gh auth status >/dev/null 2>&1 || {
  echo "ERROR: gh not authenticated. Run: gh auth login" >&2
  exit 1
}

[[ -n "$REPO" ]] || REPO="$(gh repo view --json nameWithOwner --jq '.nameWithOwner')"

POLICY_JSON="$(databricks cluster-policies list --profile "$PROFILE" --output json)"
POLICY_ID="$(printf '%s' "$POLICY_JSON" | POLICY_NAME="$POLICY_NAME" python3 -c '
import json, os, sys
name = os.environ.get("POLICY_NAME", "").strip()
raw = json.load(sys.stdin)

def candidates(r):
    if isinstance(r, list):
        return r
    if isinstance(r, dict):
        for key in ("policies", "items", "cluster_policies"):
            if key in r and isinstance(r[key], list):
                return r[key]
    return []

rows = candidates(raw)
for row in rows:
    if not isinstance(row, dict):
        continue
    if row.get("name") != name:
        continue
    pid = row.get("policy_id") or row.get("id")
    if pid:
        print(pid)
        sys.exit(0)
sys.exit(1)
')"

[[ -n "$POLICY_ID" ]] || {
  echo "ERROR: No cluster policy named \"${POLICY_NAME}\" in workspace for profile \"${PROFILE}\"." >&2
  echo "Apply Terraform (document_intelligence_stack) with enable_databricks_compute_guardrails = true first." >&2
  exit 1
}

if [[ "$APPLY" == "true" ]]; then
  gh api --silent --method PUT "repos/$REPO/environments/$GITHUB_ENV_NAME"
  printf '%s' "$POLICY_ID" | gh secret set DATABRICKS_COMPUTE_GUARDRAILS_POLICY_ID --repo "$REPO" --env "$GITHUB_ENV_NAME"
  echo "Set DATABRICKS_COMPUTE_GUARDRAILS_POLICY_ID on repo $REPO environment $GITHUB_ENV_NAME (value hidden)."
else
  echo "DRY-RUN: would set secret DATABRICKS_COMPUTE_GUARDRAILS_POLICY_ID on $REPO env $GITHUB_ENV_NAME"
  echo "         policy id: $POLICY_ID"
  echo "Re-run with --apply to write."
fi
