#!/usr/bin/env bash
set -euo pipefail

echo "Running runtime-stack Terraform checks..."

terraform -chdir=infra/terraform/gcp/runtime_stack fmt -check
terraform -chdir=infra/terraform/gcp/runtime_stack init -backend=false -input=false
terraform -chdir=infra/terraform/gcp/runtime_stack validate

for env in dev staging prod; do
  tfvars_file="infra/env/${env}/runtime.gcp.tfvars.example"
  if [[ ! -f "${tfvars_file}" ]]; then
    echo "Missing ${tfvars_file}" >&2
    exit 1
  fi
  if ! rg -q "^environment\\s*=\\s*\"${env}\"$" "${tfvars_file}"; then
    echo "Unexpected environment value in ${tfvars_file}" >&2
    exit 1
  fi
done

echo "Runtime-stack checks passed."
