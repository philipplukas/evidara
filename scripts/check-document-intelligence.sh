#!/usr/bin/env bash
set -euo pipefail

REPO_ROOT="$(cd "$(dirname "${BASH_SOURCE[0]}")/.." && pwd)"

echo "Validating shared JSON schemas..."
cd "$REPO_ROOT"
python3 scripts/validate_json_schemas.py

echo "Checking document-intelligence package..."
cd "$REPO_ROOT/document-intelligence"
if ! python3 -c 'import sys; assert sys.version_info >= (3, 12), "need 3.12+"' 2>/dev/null; then
  echo "error: document-intelligence requires Python >= 3.12 (got $(python3 -V 2>/dev/null || echo unknown))" >&2
  echo "hint: use uv (e.g. cd document-intelligence && uv sync --extra dev --extra service --extra test && uv run pytest tests/ -v)" >&2
  exit 1
fi
# Keep in sync with .github/workflows/document-intelligence.yml (dev + service + test + llm).
#
# This installs `pyproject.toml`'s FLOORS, resolved against PyPI on the day it runs — the
# early-warning axis, deliberately NOT the dependency set that ships. The Dockerfiles install
# from `uv.lock` (`uv sync --frozen`), and the `document-intelligence-locked` CI job is what
# runs the suite against that. Do not "fix" the divergence by pointing this script at the lock:
# then nothing would notice a breaking `deltalake`/`pyarrow` release until someone re-locked.
# See #848 and the dependency-set table in CLAUDE.md.
#
# `llm` is here for coverage, not for the runtime. It carries `dspy`, and without it
# `tests/test_dspy_modules.py` (11 tests) was dropped at collection and
# `test_eval_dspy_extraction.py::test_eval_harness_runs_mock` skipped — 12 tests over
# `extractors/dspy_modules.py`, which is on the production extraction path, executing
# nowhere while their docstring advertised CI mock coverage (#685). These tests mock the
# LM layer, so they need the import, not credentials or a network.
python3 -m pip install -e ".[dev,service,test,llm]"

echo "Linting (ruff check)..."
python3 -m ruff check .

echo "Format check (ruff format)..."
python3 -m ruff format --check .

echo "Running tests (pytest)..."
python3 -m pytest tests/ -v

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
