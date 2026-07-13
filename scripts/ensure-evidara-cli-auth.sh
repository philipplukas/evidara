#!/usr/bin/env bash
# Ensure the GitHub and Google Cloud CLIs are logged in (interactive).
# Run from repo root before scripts/sync-github-cd-config.sh or Terraform work.
#
# Usage:
#   scripts/ensure-evidara-cli-auth.sh
#   scripts/ensure-evidara-cli-auth.sh --skip-adc
set -euo pipefail

SKIP_ADC="false"

usage() {
  cat <<'EOF'
Usage: scripts/ensure-evidara-cli-auth.sh [options]

Options:
  --skip-adc        Do not prompt for application-default credentials (Terraform google provider)
  -h, --help
EOF
}

while [[ $# -gt 0 ]]; do
  case "$1" in
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

echo "=== Evidara CLI auth check ==="
ensure_gh
ensure_gcloud_user
ensure_gcloud_adc
echo "=== Done ==="
