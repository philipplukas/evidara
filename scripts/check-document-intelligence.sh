#!/usr/bin/env bash
set -euo pipefail

cd document-intelligence

echo "Running document-intelligence lint checks..."
python3 -m ruff check src tests
python3 -m ruff format --check src tests

echo "Running document-intelligence test suite..."
python3 -m unittest discover -s tests -v
