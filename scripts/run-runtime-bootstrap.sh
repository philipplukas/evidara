#!/usr/bin/env bash
set -euo pipefail

ENVIRONMENT="${1:-staging}"
PROJECT_ID="${GCP_PROJECT_ID:?set GCP_PROJECT_ID}"
REGION="${GCP_REGION:-europe-west6}"

if [[ "${ENVIRONMENT}" != "staging" ]]; then
  echo "This bootstrap helper currently supports staging only." >&2
  exit 1
fi

run_job() {
  local job_name="$1"
  echo "▶ Executing job: ${job_name}-${ENVIRONMENT}"
  gcloud run jobs execute "${job_name}-${ENVIRONMENT}" \
    --project "${PROJECT_ID}" \
    --region "${REGION}" \
    --wait
}

run_job "platform-control-db-migrate"

# The documents index + aliases are created by the legal-search-api startup
# bootstrap from the canonical mapping (#713) — there is no os-alias-bootstrap
# job to run. `os-alias-check` is the read-only preflight over its result.
run_job "os-alias-check"

echo "✅ Runtime bootstrap complete for ${ENVIRONMENT}."
