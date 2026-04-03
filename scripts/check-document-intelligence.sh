#!/usr/bin/env bash
set -euo pipefail

REPO_ROOT="$(cd "$(dirname "${BASH_SOURCE[0]}")/.." && pwd)"

echo "Validating shared JSON schemas..."
cd "$REPO_ROOT"
python3 scripts/validate_json_schemas.py

echo "Checking document-intelligence package..."
cd "$REPO_ROOT/document-intelligence"
python3 -m pip install -e ".[dev]"

echo "Linting (ruff check)..."
python3 -m ruff check .

echo "Format check (ruff format)..."
python3 -m ruff format --check .

echo "Running unit tests..."
python3 -m unittest discover -s tests -v

echo "Linting DI OpenAPI contracts..."
cd "$REPO_ROOT"
npx --yes @redocly/cli@latest lint \
  contracts/api/document-intelligence.openapi.yaml \
  contracts/api/document-intelligence-runtime.openapi.yaml \
  --config .redocly.yaml

echo "Validating dbt project shape..."
cd "$REPO_ROOT/document-intelligence"
python3 -m pip install dbt-core dbt-databricks
python3 -m dbt.cli.main deps --project-dir "$REPO_ROOT/document-intelligence/dbt"
python3 -m dbt.cli.main parse \
  --project-dir "$REPO_ROOT/document-intelligence/dbt" \
  --profiles-dir "$REPO_ROOT/document-intelligence/dbt" \
  --target dev
