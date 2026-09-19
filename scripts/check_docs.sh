#!/usr/bin/env bash
set -euo pipefail

echo "Validating documentation..."

# 1. Validate contracts and schemas
python3 scripts/validate_openapi.py
python3 scripts/validate_json_schemas.py
python3 scripts/check_contract_manifest.py
python3 scripts/check_platform_contract_vendor.py
bash scripts/validate_hetzner_apps_kustomize.sh

# 2. Check doc structure
python3 scripts/check_component_docs.py
python3 scripts/check_runbooks.py
python3 scripts/check_doc_links.py
python3 scripts/check_diagram_format.py
npm run --silent check:mermaid

# 3. Check the pointers the docs carry are still true.
#
#    Prose that names a live thing rots silently: CLAUDE.md's planning anchor
#    named a closed issue for three days, then a second closed issue for six
#    more, while documenting that exact failure in its own text. These four
#    assert that a rule still describes the code, the issue, or the surface it
#    claims to.
python3 scripts/check_planning_anchor.py
python3 scripts/check_classifier_evidence_rule.py
python3 scripts/check_measured_premise.py
python3 scripts/check_api_version_lane.py

# 4. Build docs site (strict mode catches broken cross-references).
#    Writes ./site/ (gitignored); do not commit. See docs/documentation/README.md.
echo "Building docs site (strict mode)..."
python3 -m mkdocs build --strict --quiet

echo "All documentation checks passed."
