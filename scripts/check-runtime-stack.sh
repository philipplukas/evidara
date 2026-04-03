#!/usr/bin/env bash
set -euo pipefail

echo "Running runtime-stack Terraform checks..."

terraform -chdir=infra/terraform/gcp/runtime_stack fmt -check
terraform -chdir=infra/terraform/gcp/runtime_stack init -backend=false -input=false
terraform -chdir=infra/terraform/gcp/runtime_stack validate

for env in dev staging prod; do
  runtime_tfvars_file="infra/env/${env}/runtime.gcp.tfvars.example"
  if [[ ! -f "${runtime_tfvars_file}" ]]; then
    echo "Missing ${runtime_tfvars_file}" >&2
    exit 1
  fi
  if ! grep -Eq "^environment[[:space:]]*=[[:space:]]*\"${env}\"$" "${runtime_tfvars_file}"; then
    echo "Unexpected environment value in ${runtime_tfvars_file}" >&2
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
