#!/usr/bin/env bash
# Regenerate staging relevance table (see docs/runbooks/staging-relevance-query-pack-suggestions.md).
# Usage: STAGING_LEGAL_SEARCH_URL=https://... ./scripts/capture-staging-relevance-pack.sh [output.md]
set -euo pipefail

REPO_ROOT="$(cd "$(dirname "${BASH_SOURCE[0]}")/.." && pwd)"
BASE_URL="${STAGING_LEGAL_SEARCH_URL:-https://legal-search-api-staging-kxc5agexna-oa.a.run.app}"
BASE_URL="${BASE_URL%/}"
OUT="${1:-${REPO_ROOT}/docs/runbooks/evidence/$(date -u +%Y-%m-%d)-staging-relevance-pack.md}"

QUERIES=(
  "Bundesgericht"
  "BGE 133 III 393"
  "OR Art. 260"
  "Mietrecht Kündigung"
  "Strafrecht"
  "Bundesgesetz über die"
  "BVGE"
  "Datenschutz DSG"
  "Verwaltungsgericht"
  "Zivilprozessordnung"
)

tmp="$(mktemp)"
trap 'rm -f "$tmp"' EXIT

{
  echo "# Staging relevance pack capture ($(date -u +%Y-%m-%dT%H:%MZ))"
  echo ""
  echo "**API:** \`${BASE_URL}\`"
  echo ""
  echo "**Note:** Re-run after corpus or ranking changes. List API does not expose per-hit scores — marked \`n/a\`."
  echo ""
  echo '| # | Query text | Top 1 `document_id` | Top 1 score | Top 2 `document_id` | Top 2 score | Top 3 `document_id` | Top 3 score | Expected doc in top 5? | Notes |'
  echo "|---|------------|------------------------|-------------|------------------------|-------------|------------------------|-------------|------------------------|-------|"
} >"$tmp"

i=0
for q in "${QUERIES[@]}"; do
  i=$((i + 1))
  enc="$(python3 -c "import urllib.parse,sys; print(urllib.parse.quote(sys.argv[1]))" "$q")"
  json="$(curl -fsS --connect-timeout 5 --max-time 30 "${BASE_URL}/v1/search?q=${enc}&page=1&page_size=3")"
  readarray -t ids < <(echo "$json" | python3 -c "import json,sys; d=json.load(sys.stdin); r=d.get('results')or[]; print('\n'.join((x.get('id')or'') for x in r[:3]))")
  while [[ ${#ids[@]} -lt 3 ]]; do ids+=(""); done
  echo "| $i | $q | ${ids[0]:-} | n/a | ${ids[1]:-} | n/a | ${ids[2]:-} | n/a | TBD | |" >>"$tmp"
done

mkdir -p "$(dirname "$OUT")"
cp "$tmp" "$OUT"
echo "Wrote $OUT"
