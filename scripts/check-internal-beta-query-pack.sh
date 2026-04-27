#!/usr/bin/env bash
# Assert the internal-beta staging corpus returns expected documents in top 5.
#
# Usage:
#   EVIDARA_LEGAL_SEARCH_URL=http://127.0.0.1:18080 \
#     ./scripts/check-internal-beta-query-pack.sh

set -euo pipefail

ROOT="$(cd "$(dirname "$0")/.." && pwd)"
EXPECTED_FILE="${1:-$ROOT/scripts/fixtures/internal-beta-staging-expected.tsv}"
BASE_URL="${EVIDARA_LEGAL_SEARCH_URL:-}"
TOKEN="${EVIDARA_LEGAL_SEARCH_TOKEN:-}"

if [[ -z "$BASE_URL" ]]; then
  echo "Set EVIDARA_LEGAL_SEARCH_URL." >&2
  exit 2
fi

if [[ ! -f "$EXPECTED_FILE" ]]; then
  echo "Expected-query file not found: $EXPECTED_FILE" >&2
  exit 2
fi

BASE_URL="${BASE_URL%/}"
failures=0
row=0

echo "## Internal beta query pack"
echo ""
echo "| # | Query | Expected | Top 5 | Status |"
echo "|---|-------|----------|-------|--------|"

while IFS=$'\t' read -r query expected notes || [[ -n "${query:-}" ]]; do
  query="${query//$'\r'/}"
  expected="${expected//$'\r'/}"
  [[ -z "${query// }" ]] && continue
  [[ "$query" =~ ^[[:space:]]*# ]] && continue
  row=$((row + 1))

  enc="$(python3 -c "import urllib.parse,sys; print(urllib.parse.quote(sys.argv[1]))" "$query")"
  url="${BASE_URL}/v1/search?q=${enc}&page_size=5"
  curl_args=(-fsS "$url" -H "Accept: application/json")
  if [[ -n "$TOKEN" ]]; then
    curl_args+=(-H "Authorization: Bearer ${TOKEN}")
  fi
  body="$(curl "${curl_args[@]}")"

  export BETA_QUERY="$query"
  export BETA_EXPECTED="$expected"
  export BETA_BODY="$body"
  if ! status_row="$(python3 <<'PY'
import json
import os
import sys

query = os.environ["BETA_QUERY"]
expected = os.environ["BETA_EXPECTED"]
body = json.loads(os.environ["BETA_BODY"])
results = body.get("results") or []
ids = [str(row.get("id") or row.get("document_id") or "") for row in results[:5]]
total = int(body.get("totalResults") or body.get("total_results") or len(results))

query_cell = query.replace("|", "\\|")
expected_cell = expected.replace("|", "\\|")
top5_cell = ", ".join(ids).replace("|", "\\|")
if expected == "__nonempty__":
    ok = total > 0
else:
    ok = expected in ids
status = "pass" if ok else "fail"
print(f"{query_cell}\t{expected_cell}\t{top5_cell}\t{status}")
sys.exit(0 if ok else 1)
PY
)"; then
    failures=$((failures + 1))
  fi

  IFS=$'\t' read -r query_cell expected_cell top5_cell status <<<"$status_row"
  echo "| $row | $query_cell | $expected_cell | $top5_cell | $status |"
done < "$EXPECTED_FILE"

if (( failures > 0 )); then
  echo "" >&2
  echo "Internal beta query pack failed: $failures expectation(s) missed." >&2
  exit 1
fi

echo ""
echo "Internal beta query pack passed."
