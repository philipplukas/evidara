#!/usr/bin/env bash
set -euo pipefail

cd platform-control

uv run ruff check .
uv run ruff format --check .
uv run pytest
