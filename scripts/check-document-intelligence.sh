#!/usr/bin/env bash
set -euo pipefail

REPO_ROOT="$(cd "$(dirname "${BASH_SOURCE[0]}")/.." && pwd)"

echo "Validating shared JSON schemas..."
cd "$REPO_ROOT"
python3 scripts/validate_json_schemas.py

echo "Checking document-intelligence package..."
cd "$REPO_ROOT/document-intelligence"
python3 -m pip install -e .
python3 -m unittest discover -s tests -v

echo "Validating dbt project shape..."
python3 -m pip install dbt-core dbt-databricks
python3 -m dbt.cli.main deps --project-dir "$REPO_ROOT/document-intelligence/dbt"
python3 -m dbt.cli.main parse \
  --project-dir "$REPO_ROOT/document-intelligence/dbt" \
  --profiles-dir "$REPO_ROOT/document-intelligence/dbt" \
  --target dev
