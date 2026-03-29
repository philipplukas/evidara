#!/usr/bin/env bash
set -euo pipefail

echo "Validating documentation..."

# 1. Validate contracts and schemas
python3 scripts/validate_openapi.py
python3 scripts/validate_json_schemas.py

# 2. Check doc structure
python3 scripts/check_component_docs.py
python3 scripts/check_runbooks.py
python3 scripts/check_doc_links.py

# 3. Build docs site (strict mode catches broken cross-references)
echo "Building docs site (strict mode)..."
mkdocs build --strict --quiet

echo "All documentation checks passed."
