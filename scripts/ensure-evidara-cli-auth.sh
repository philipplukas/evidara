#!/usr/bin/env bash
# Ensure GitHub, Google Cloud, and Databricks CLIs are logged in (interactive).
# Run from repo root before scripts/sync-github-cd-config.sh or Terraform/bundle work.
#
# Usage:
#   scripts/ensure-evidara-cli-auth.sh
#   scripts/ensure-evidara-cli-auth.sh --profiles dev,staging,prod
#   scripts/ensure-evidara-cli-auth.sh --skip-adc
set -euo pipefail

PROFILES=(dev staging prod)
SKIP_ADC="false"

usage() {
  cat <<'EOF'
Usage: scripts/ensure-evidara-cli-auth.sh [options]

Options:
  --profiles LIST   Comma-separated Databricks ~/.databrickscfg profiles (default: dev,staging,prod)
  --skip-adc        Do not prompt for application-default credentials (Terraform google provider)
  -h, --help
EOF
}

while [[ $# -gt 0 ]]; do
  case "$1" in
    --profiles)
      IFS=',' read -r -a PROFILES <<<"$2"
      shift 2
      ;;
    --skip-adc) SKIP_ADC="true"; shift ;;
    -h|--help) usage; exit 0 ;;
    *) echo "Unknown option: $1" >&2; usage >&2; exit 1 ;;
  esac
done

require_cmd() {
  command -v "$1" >/dev/null 2>&1 || {
    echo "ERROR: missing command '$1'" >&2
    exit 1
  }
}

confirm() {
  local answer=""
  read -r -p "$1 [y/N]: " answer || true
  [[ "$answer" == "y" || "$answer" == "Y" ]]
}

ensure_gh() {
  require_cmd gh
  if gh auth status &>/dev/null; then
    echo "GitHub CLI: already authenticated."
    return
  fi
  echo "GitHub CLI: not authenticated."
  if confirm "Run 'gh auth login'?"; then
    gh auth login
  else
    echo "ERROR: gh auth required for GitHub Actions secret sync." >&2
    exit 1
  fi
}

ensure_gcloud_user() {
  require_cmd gcloud
  if gcloud auth list --filter=status:ACTIVE --format='value(account)' 2>/dev/null | grep -q .; then
    echo "gcloud user: active account configured."
    return
  fi
  echo "gcloud: no active user account."
  if confirm "Run 'gcloud auth login'?"; then
    gcloud auth login
  else
    echo "ERROR: gcloud user login required for GCP project/Secret Manager access." >&2
    exit 1
  fi
}

ensure_gcloud_adc() {
  [[ "$SKIP_ADC" == "true" ]] && return
  require_cmd gcloud
  if gcloud auth application-default print-access-token &>/dev/null; then
    echo "gcloud ADC: already configured."
    return
  fi
  echo "gcloud: application-default credentials missing (common for local Terraform)."
  if confirm "Run 'gcloud auth application-default login'?"; then
    gcloud auth application-default login
  fi
}

databricks_profile_ok() {
  local p="$1"
  databricks auth env --profile "$p" --output json 2>/dev/null | python3 -c '
import json, sys
try:
    d = json.load(sys.stdin)
    t = (d.get("env") or {}).get("DATABRICKS_TOKEN") or ""
    sys.exit(0 if len(t) > 8 else 1)
except Exception:
    sys.exit(1)
'
}

ensure_databricks_profiles() {
  require_cmd databricks
  require_cmd python3
  local p failed=0
  for p in "${PROFILES[@]}"; do
    [[ -n "$p" ]] || continue
    if databricks_profile_ok "$p"; then
      echo "Databricks profile '$p': OK"
      continue
    fi
    echo "Databricks profile '$p': not authenticated (or token empty)."
    if confirm "Run 'databricks auth login' for profile '$p'?"; then
      if databricks auth login --profile "$p" 2>/dev/null; then
        :
      else
        echo "  Retrying with DATABRICKS_CONFIG_PROFILE=$p …"
        DATABRICKS_CONFIG_PROFILE="$p" databricks auth login || failed=$((failed + 1))
      fi
    else
      failed=$((failed + 1))
    fi
  done
  (( failed == 0 )) || {
    echo "ERROR: one or more Databricks profiles still not authenticated." >&2
    exit 1
  }
}

echo "=== Evidara CLI auth check ==="
ensure_gh
ensure_gcloud_user
ensure_gcloud_adc
ensure_databricks_profiles
echo "=== Done ==="
