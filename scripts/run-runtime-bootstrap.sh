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
run_job "os-alias-bootstrap"
run_job "os-alias-check"

echo "✅ Runtime bootstrap complete for ${ENVIRONMENT}."
