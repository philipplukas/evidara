#!/usr/bin/env bash
set -euo pipefail

cd document-intelligence

python -m pip install --upgrade pip
python -m pip install uv
uv pip install -e ".[service]"
python -m unittest discover -s tests -v
