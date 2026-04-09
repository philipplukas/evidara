#!/usr/bin/env bash
set -euo pipefail

# Mint audience-scoped Cloud Run ID tokens for local operator workflows.
#
# Required environment:
#   EVIDARA_GCP_IMPERSONATE_SERVICE_ACCOUNT — SA email (needs run.invoker on both services)
#   EVIDARA_PLATFORM_CONTROL_URL — platform-control API base (no path), e.g. https://…run.app
#   EVIDARA_LEGAL_SEARCH_URL — legal-search BFF base (no path)
#
# Optional overrides for URL names only:
#   MINT_PLATFORM_CONTROL_URL, MINT_LEGAL_SEARCH_URL
#
# Usage (from repo root, after gcloud user login):
#   eval "$(
#     EVIDARA_GCP_IMPERSONATE_SERVICE_ACCOUNT='sa@project.iam.gserviceaccount.com' \
#     EVIDARA_PLATFORM_CONTROL_URL='https://platform-control-api-staging-….run.app' \
#     EVIDARA_LEGAL_SEARCH_URL='https://legal-search-api-staging-….run.app' \
#     ./scripts/mint-cloud-run-tokens.sh
#   )"
#
# Then: uv run evidara workflow mvp-acceptance --human
# Or set E2E_* for scripts/e2e-smoke-test.sh when URLs match those hosts.
#
# Requires: gcloud, roles/iam.serviceAccountTokenCreator on the SA for your user.

SA="${EVIDARA_GCP_IMPERSONATE_SERVICE_ACCOUNT:?Set EVIDARA_GCP_IMPERSONATE_SERVICE_ACCOUNT}"
PC_RAW="${EVIDARA_PLATFORM_CONTROL_URL:-${MINT_PLATFORM_CONTROL_URL:-}}"
LS_RAW="${EVIDARA_LEGAL_SEARCH_URL:-${MINT_LEGAL_SEARCH_URL:-}}"
PC_BASE="${PC_RAW%/}"
LS_BASE="${LS_RAW%/}"

if [[ -z "${PC_BASE}" || -z "${LS_BASE}" ]]; then
  echo "Set EVIDARA_PLATFORM_CONTROL_URL and EVIDARA_LEGAL_SEARCH_URL (or MINT_* equivalents)." >&2
  exit 1
fi

if ! command -v gcloud >/dev/null 2>&1; then
  echo "gcloud CLI is required." >&2
  exit 1
fi

PC_TOKEN="$(gcloud auth print-identity-token --impersonate-service-account="${SA}" --audiences="${PC_BASE}")"
LS_TOKEN="$(gcloud auth print-identity-token --impersonate-service-account="${SA}" --audiences="${LS_BASE}")"

printf 'export EVIDARA_PLATFORM_CONTROL_TOKEN=%q\n' "${PC_TOKEN}"
printf 'export EVIDARA_LEGAL_SEARCH_TOKEN=%q\n' "${LS_TOKEN}"
printf 'export E2E_PC_ID_TOKEN=%q\n' "${PC_TOKEN}"
printf 'export E2E_LS_ID_TOKEN=%q\n' "${LS_TOKEN}"
