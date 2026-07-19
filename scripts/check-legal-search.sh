#!/usr/bin/env bash
#
# Local entry point for the legal-search gates (api + frontend).
#
# PARITY (#688): this script and `.github/workflows/legal-search.yml` must run
# the same `npm run` commands per surface. CI deliberately does NOT shell out to
# this script — it splits `api` and `frontend` into parallel jobs, each with its
# own `npm ci` cache keyed on that surface's package-lock.json, which routing
# through one serial script would give up. So parity is enforced by a test
# instead of by shared invocation:
#
#   scripts/tests/test_check_legal_search_parity.py
#
# It parses both files and fails if the command sets diverge. Add a gate here
# and to the workflow, or that test fails.
#
# Note `npm run check` already includes `openapi:lint` and `openapi:check` in
# the frontend (see legal-search/frontend/package.json). This script used to
# re-run both explicitly, which read as "CI is missing the OpenAPI drift gate"
# when in fact CI runs it inside `check`.
#
# The repo-wide JS hygiene invariants are a separate concern with their own
# entry point (scripts/check-js-workspace-hygiene.sh), its own CI job, and its
# own pre-commit hook.

set -euo pipefail

repo_root="$(cd "$(dirname "${BASH_SOURCE[0]}")/.." && pwd)"

echo "Checking legal-search API..."
cd "$repo_root/legal-search/api"
npm ci
npm run check

echo "Checking legal-search frontend..."
cd "$repo_root/legal-search/frontend"
npm ci
npm run check
# Build separately — catches SSR issues tsc misses (mirrors the workflow).
npm run build
