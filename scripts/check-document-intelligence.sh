#!/usr/bin/env bash
set -euo pipefail

cd document-intelligence

py="${PYTHON:-python3}"
command -v "$py" >/dev/null 2>&1 || py="python"

"$py" -m pip install --upgrade pip
"$py" -m pip install -e ".[service]"
"$py" -m unittest discover -s tests -v
