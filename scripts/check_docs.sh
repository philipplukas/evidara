#!/usr/bin/env bash
set -euo pipefail

echo "Validating documentation..."

# 1. Validate contracts and schemas
python3 scripts/validate_openapi.py
python3 scripts/validate_json_schemas.py
python3 scripts/check_contract_manifest.py
python3 scripts/check_platform_contract_vendor.py

# 2. Check doc structure
python3 scripts/check_component_docs.py
python3 scripts/check_runbooks.py
python3 scripts/check_doc_links.py
python3 scripts/check_diagram_format.py
npm run --silent check:mermaid

# 3. Build docs site (strict mode catches broken cross-references).
#    Writes ./site/ (gitignored); do not commit. See docs/documentation/README.md.
echo "Building docs site (strict mode)..."
python3 -m mkdocs build --strict --quiet

echo "All documentation checks passed."
