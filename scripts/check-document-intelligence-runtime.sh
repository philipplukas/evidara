#!/usr/bin/env bash
set -euo pipefail

echo "Running document-intelligence Databricks/Terraform runtime checks..."

terraform -chdir=infra/terraform/databricks/document_intelligence fmt -check
terraform -chdir=infra/terraform/databricks/document_intelligence_stack fmt -check

terraform -chdir=infra/terraform/databricks/document_intelligence init -backend=false -input=false
terraform -chdir=infra/terraform/databricks/document_intelligence validate

terraform -chdir=infra/terraform/databricks/document_intelligence_stack init -backend=false -input=false
terraform -chdir=infra/terraform/databricks/document_intelligence_stack validate

echo "All document-intelligence runtime checks passed."
