#!/usr/bin/env bash
set -euo pipefail

echo "Running runtime-stack Terraform checks..."

terraform -chdir=infra/terraform/gcp/runtime_stack fmt -check
terraform -chdir=infra/terraform/gcp/runtime_stack init -backend=false -input=false
terraform -chdir=infra/terraform/gcp/runtime_stack validate

for env in dev staging prod; do
  runtime_tfvars_file="infra/env/${env}/runtime.gcp.tfvars.example"
  case "${env}" in
    dev) expected_project_id="evidara-dev" ;;
    staging) expected_project_id="evidara-staging" ;;
    prod) expected_project_id="evidara-prod" ;;
  esac
  if [[ ! -f "${runtime_tfvars_file}" ]]; then
    echo "Missing ${runtime_tfvars_file}" >&2
    exit 1
  fi
  if ! grep -Eq "^environment[[:space:]]*=[[:space:]]*\"${env}\"$" "${runtime_tfvars_file}"; then
    echo "Unexpected environment value in ${runtime_tfvars_file}" >&2
    exit 1
  fi
  if ! grep -Eq "^project_id[[:space:]]*=[[:space:]]*\"${expected_project_id}\"$" "${runtime_tfvars_file}"; then
    echo "Unexpected project_id in ${runtime_tfvars_file}" >&2
    exit 1
  fi
  if ! grep -Eq "DI_GCP_PROJECT_ID[[:space:]]*=[[:space:]]*\"${expected_project_id}\"" "${runtime_tfvars_file}"; then
    echo "Missing or unexpected DI_GCP_PROJECT_ID in ${runtime_tfvars_file}" >&2
    exit 1
  fi
  if ! grep -Eq "DI_STATUS_TOPIC_NAME[[:space:]]*=[[:space:]]*\"document-processing-status-updated\"" "${runtime_tfvars_file}"; then
    echo "Missing or unexpected DI_STATUS_TOPIC_NAME in ${runtime_tfvars_file}" >&2
    exit 1
  fi
  if ! grep -Eq "DI_PROCESSED_TOPIC_NAME[[:space:]]*=[[:space:]]*\"document-processed\"" "${runtime_tfvars_file}"; then
    echo "Missing or unexpected DI_PROCESSED_TOPIC_NAME in ${runtime_tfvars_file}" >&2
    exit 1
  fi

  opensearch_tfvars_file="infra/env/${env}/opensearch.gke.tfvars.example"
  if [[ ! -f "${opensearch_tfvars_file}" ]]; then
    echo "Missing ${opensearch_tfvars_file}" >&2
    exit 1
  fi
  if ! grep -Eq "^environment[[:space:]]*=[[:space:]]*\"${env}\"$" "${opensearch_tfvars_file}"; then
    echo "Unexpected environment value in ${opensearch_tfvars_file}" >&2
    exit 1
  fi
done

echo "Runtime-stack checks passed (runtime + opensearch env tfvars)."
