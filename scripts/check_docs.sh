#!/usr/bin/env bash
set -euo pipefail

python3 scripts/validate_openapi.py
python3 scripts/validate_json_schemas.py
python3 scripts/check_component_docs.py
python3 scripts/check_runbooks.py
python3 scripts/check_doc_links.py
