#!/usr/bin/env bash
set -euo pipefail
REPO_ROOT="$(cd "$(dirname "${BASH_SOURCE[0]}")/.." && pwd)"
cd "$REPO_ROOT/tools/evidara-cli"
uv sync --group dev --quiet
uv run ruff check src tests
uv run ruff format --check src tests
uv run pytest -q
