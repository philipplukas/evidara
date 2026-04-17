#!/usr/bin/env bash
# Run the search relevance query pack (TAR-82 / TAR-68) against a deployed legal-search API.
# Works for **dev**, staging, or any URL — set EVIDARA_LEGAL_SEARCH_URL accordingly (dev-first teams use dev Cloud Run).
# Outputs a Markdown table for docs/runbooks/relevance-eval-result-template.md
#
# Usage (from repo root):
#   export EVIDARA_LEGAL_SEARCH_URL="https://…legal-search-api-staging….run.app"
#   export EVIDARA_LEGAL_SEARCH_TOKEN="…"   # Bearer (e.g. mint-cloud-run-tokens.sh)
#   ./scripts/run-staging-relevance-query-pack.sh [queries-file]
#
# Default queries file: scripts/fixtures/staging-relevance-queries.example.txt

set -euo pipefail

ROOT="$(cd "$(dirname "$0")/.." && pwd)"
QUERIES_FILE="${1:-$ROOT/scripts/fixtures/staging-relevance-queries.example.txt}"
BASE_URL="${EVIDARA_LEGAL_SEARCH_URL:-}"
TOKEN="${EVIDARA_LEGAL_SEARCH_TOKEN:-}"

if [[ -z "$BASE_URL" || -z "$TOKEN" ]]; then
  echo "Set EVIDARA_LEGAL_SEARCH_URL and EVIDARA_LEGAL_SEARCH_TOKEN (Bearer)." >&2
  exit 2
fi

BASE_URL="${BASE_URL%/}"

if [[ ! -f "$QUERIES_FILE" ]]; then
  echo "Queries file not found: $QUERIES_FILE" >&2
  exit 2
fi

echo "## Staging relevance query pack (generated)"
echo ""
echo "- **API:** \`${BASE_URL}\`"
echo "- **Queries file:** \`${QUERIES_FILE}\`"
echo "- **Generated at (UTC):** $(date -u +%Y-%m-%dT%H:%M:%SZ)"
echo ""
echo "| # | Query | rank1_doc_id | rank1_score | rank2_doc_id | rank2_score | rank3_doc_id | rank3_score | expected_in_top5 | notes |"
echo "|---|-------|--------------|-------------|--------------|-------------|--------------|-------------|------------------|-------|"

row=0
while IFS= read -r line || [[ -n "$line" ]]; do
  q="${line//$'\r'/}"
  [[ -z "${q// }" ]] && continue
  [[ "$q" =~ ^[[:space:]]*# ]] && continue
  row=$((row + 1))

  enc="$(python3 -c "import urllib.parse,sys; print(urllib.parse.quote(sys.argv[1]))" "$q")"
  url="${BASE_URL}/v1/search?q=${enc}&page_size=5"
  body="$(curl -fsS "$url" -H "Authorization: Bearer ${TOKEN}" -H "Accept: application/json")"

  export RELEVANCE_PACK_QUERY="$q"
  export RELEVANCE_PACK_ROW="$row"
  export RELEVANCE_PACK_BODY="$body"
  python3 <<'PY'
import json
import os

query = os.environ["RELEVANCE_PACK_QUERY"]
idx = os.environ["RELEVANCE_PACK_ROW"]
raw = os.environ["RELEVANCE_PACK_BODY"]
q_disp = query.replace("|", "\\|").replace("\n", " ")
try:
    data = json.loads(raw)
except json.JSONDecodeError as e:
    print(f"| {idx} | {q_disp!r} | | | | | | | | | **parse_error:** {e} |")
    raise SystemExit(0)

results = data.get("results") or []
cells: list[str] = []
for i in range(3):
    if i < len(results):
        r = results[i]
        did = str(r.get("id") or r.get("document_id") or "")
        sc = str(r.get("relevance_score") or r.get("score") or "")
        cells.extend([did, sc])
    else:
        cells.extend(["", ""])

print(
    f"| {idx} | {q_disp} | {cells[0]} | {cells[1]} | {cells[2]} | {cells[3]} | {cells[4]} | {cells[5]} |  |  |"
)
PY
done < "$QUERIES_FILE"

echo ""
echo "_Fill \`expected_in_top5\` and \`notes\` per [relevance-eval-result-template.md](../docs/runbooks/relevance-eval-result-template.md); attach to Linear TAR-82 / TAR-68._"
