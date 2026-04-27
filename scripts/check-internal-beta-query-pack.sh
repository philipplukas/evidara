#!/usr/bin/env bash
# Assert the internal-beta staging corpus returns expected beta evidence.
#
# Usage:
#   EVIDARA_LEGAL_SEARCH_URL=http://127.0.0.1:18080 \
#     ./scripts/check-internal-beta-query-pack.sh

set -euo pipefail

ROOT="$(cd "$(dirname "$0")/.." && pwd)"
EXPECTED_FILE="${1:-$ROOT/scripts/fixtures/internal-beta-staging-expected.tsv}"
DETAIL_EXPECTATIONS_FILE="${INTERNAL_BETA_DETAIL_EXPECTATIONS_FILE:-$ROOT/scripts/fixtures/internal-beta-staging-documents.tsv}"
WITHDRAWN_FILE="${INTERNAL_BETA_WITHDRAWN_FILE:-$ROOT/scripts/fixtures/internal-beta-staging-withdrawn-documents.txt}"
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

if [[ ! -f "$DETAIL_EXPECTATIONS_FILE" ]]; then
  echo "Detail expectations file not found: $DETAIL_EXPECTATIONS_FILE" >&2
  exit 2
fi

if [[ ! -f "$WITHDRAWN_FILE" ]]; then
  echo "Withdrawn-document file not found: $WITHDRAWN_FILE" >&2
  exit 2
fi

BASE_URL="${BASE_URL%/}"
failures=0
row=0
source_doc_ids="$(awk -F $'\t' 'NF && $1 !~ /^[[:space:]]*#/ && $1 !~ /^[[:space:]]*$/ {print $1}' "$DETAIL_EXPECTATIONS_FILE" | paste -sd, -)"
if [[ -z "$source_doc_ids" ]]; then
  echo "No source document IDs found in: $DETAIL_EXPECTATIONS_FILE" >&2
  exit 2
fi

curl_json() {
  local url="$1"
  local -a curl_args=(-fsS "$url" -H "Accept: application/json")
  if [[ -n "$TOKEN" ]]; then
    curl_args+=(-H "Authorization: Bearer ${TOKEN}")
  fi
  curl "${curl_args[@]}"
}

curl_code() {
  local url="$1"
  local -a curl_args=(-sS -o /dev/null -w "%{http_code}" "$url" -H "Accept: application/json")
  local code
  if [[ -n "$TOKEN" ]]; then
    curl_args+=(-H "Authorization: Bearer ${TOKEN}")
  fi
  if ! code="$(curl "${curl_args[@]}")"; then
    code="000"
  fi
  printf "%s" "$code"
}

echo "## Internal beta query pack"
echo ""
echo "| # | Query | Expected top-5 | Top 5 | totalResults | Status | Notes |"
echo "|---|-------|----------------|-------|-------------:|--------|-------|"

while IFS=$'\t' read -r query expected notes || [[ -n "${query:-}" ]]; do
  query="${query//$'\r'/}"
  expected="${expected//$'\r'/}"
  notes="${notes//$'\r'/}"
  [[ -z "${query// }" ]] && continue
  [[ "$query" =~ ^[[:space:]]*# ]] && continue
  row=$((row + 1))

  enc="$(python3 -c "import urllib.parse,sys; print(urllib.parse.quote(sys.argv[1]))" "$query")"
  url="${BASE_URL}/v1/search?q=${enc}&page_size=5"
  body="$(curl_json "$url")"

  export BETA_QUERY="$query"
  export BETA_EXPECTED="$expected"
  export BETA_NOTES="$notes"
  export BETA_BODY="$body"
  export BETA_SOURCE_DOC_IDS="$source_doc_ids"
  if ! status_row="$(python3 <<'PY'
import json
import os
import sys

query = os.environ["BETA_QUERY"]
expected = os.environ["BETA_EXPECTED"]
notes = os.environ["BETA_NOTES"]
source_ids = [x for x in os.environ["BETA_SOURCE_DOC_IDS"].split(",") if x]
body = json.loads(os.environ["BETA_BODY"])
results = body.get("results") or []
ids = [str(row.get("id") or row.get("document_id") or "") for row in results[:5]]
total = int(body.get("totalResults") or body.get("total_results") or len(results))

def cell(value: object) -> str:
    return str(value).replace("|", "\\|").replace("\n", " ")

if expected == "__exact_beta_corpus__":
    ok = total == len(source_ids) and set(ids) == set(source_ids)
    expected_cell = ", ".join(source_ids)
elif expected == "__nonempty__":
    ok = total > 0
    expected_cell = "__nonempty__"
else:
    expected_ids = [x.strip() for x in expected.split(",") if x.strip()]
    ok = bool(expected_ids) and all(doc_id in ids for doc_id in expected_ids)
    expected_cell = ", ".join(expected_ids)
status = "pass" if ok else "fail"
print(f"{cell(query)}\t{cell(expected_cell)}\t{cell(', '.join(ids))}\t{total}\t{status}\t{cell(notes)}")
sys.exit(0 if ok else 1)
PY
)"; then
    failures=$((failures + 1))
  fi

  IFS=$'\t' read -r query_cell expected_cell top5_cell total_cell status notes_cell <<<"$status_row"
  echo "| $row | $query_cell | $expected_cell | $top5_cell | $total_cell | $status | $notes_cell |"
done < "$EXPECTED_FILE"

echo ""
echo "## Source-derived detail expectations"
echo ""
echo "| # | Document ID | Title contains | Type | Metadata rows | Tabs | Status | Notes |"
echo "|---|-------------|----------------|------|--------------:|------|--------|-------|"

detail_row=0
while IFS=$'\t' read -r doc_id title_contains expected_type subtitle_contains min_metadata expected_tabs notes || [[ -n "${doc_id:-}" ]]; do
  doc_id="${doc_id//$'\r'/}"
  title_contains="${title_contains//$'\r'/}"
  expected_type="${expected_type//$'\r'/}"
  subtitle_contains="${subtitle_contains//$'\r'/}"
  min_metadata="${min_metadata//$'\r'/}"
  expected_tabs="${expected_tabs//$'\r'/}"
  notes="${notes//$'\r'/}"
  [[ -z "${doc_id// }" ]] && continue
  [[ "$doc_id" =~ ^[[:space:]]*# ]] && continue
  detail_row=$((detail_row + 1))

  body="$(curl_json "${BASE_URL}/v1/documents/${doc_id}")"
  export BETA_DETAIL_DOC_ID="$doc_id"
  export BETA_DETAIL_TITLE_CONTAINS="$title_contains"
  export BETA_DETAIL_EXPECTED_TYPE="$expected_type"
  export BETA_DETAIL_SUBTITLE_CONTAINS="$subtitle_contains"
  export BETA_DETAIL_MIN_METADATA="$min_metadata"
  export BETA_DETAIL_EXPECTED_TABS="$expected_tabs"
  export BETA_DETAIL_NOTES="$notes"
  export BETA_DETAIL_BODY="$body"
  if ! detail_status_row="$(python3 <<'PY'
import json
import os
import sys

doc_id = os.environ["BETA_DETAIL_DOC_ID"]
title_contains = os.environ["BETA_DETAIL_TITLE_CONTAINS"]
expected_type = os.environ["BETA_DETAIL_EXPECTED_TYPE"]
subtitle_contains = os.environ["BETA_DETAIL_SUBTITLE_CONTAINS"]
min_metadata = int(os.environ["BETA_DETAIL_MIN_METADATA"])
expected_tabs = [x.strip() for x in os.environ["BETA_DETAIL_EXPECTED_TABS"].split(",") if x.strip()]
notes = os.environ["BETA_DETAIL_NOTES"]
detail = json.loads(os.environ["BETA_DETAIL_BODY"])

metadata = detail.get("metadataRows")
if metadata is None:
    metadata = detail.get("metadata")
metadata = metadata if isinstance(metadata, list) else []

raw_tabs = detail.get("tabs") or []
tab_keys: list[str] = []
for tab in raw_tabs:
    if isinstance(tab, dict):
        key = tab.get("key")
    else:
        key = tab
    if key:
        tab_keys.append(str(key))

title = detail.get("title")
subtitle = detail.get("subtitle")
checks = {
    "id": detail.get("id") == doc_id,
    "title": isinstance(title, str) and title_contains in title and title != f"Document {doc_id}",
    "type": detail.get("type") == expected_type,
    "subtitle": isinstance(subtitle, str) and subtitle_contains in subtitle,
    "metadata": len(metadata) >= min_metadata,
    "tabs": all(tab in tab_keys for tab in expected_tabs),
}
ok = all(checks.values())
missing = ",".join(name for name, passed in checks.items() if not passed)

def cell(value: object) -> str:
    return str(value).replace("|", "\\|").replace("\n", " ")

print(
    f"{cell(doc_id)}\t{cell(title_contains)}\t{cell(expected_type)}\t"
    f"{len(metadata)}\t{cell(', '.join(tab_keys))}\t"
    f"{'pass' if ok else 'fail'}\t{cell(notes if ok else notes + '; failed=' + missing)}"
)
sys.exit(0 if ok else 1)
PY
)"; then
    failures=$((failures + 1))
  fi

  IFS=$'\t' read -r doc_id_cell title_cell type_cell metadata_cell tabs_cell status_cell notes_cell <<<"$detail_status_row"
  echo "| $detail_row | $doc_id_cell | $title_cell | $type_cell | $metadata_cell | $tabs_cell | $status_cell | $notes_cell |"
done < "$DETAIL_EXPECTATIONS_FILE"

echo ""
echo "## Retired synthetic document tombstones"
echo ""
echo "| # | Document ID | HTTP status | Status | Notes |"
echo "|---|-------------|------------:|--------|-------|"

withdrawn_row=0
while IFS=$'\t' read -r doc_id notes || [[ -n "${doc_id:-}" ]]; do
  doc_id="${doc_id//$'\r'/}"
  notes="${notes//$'\r'/}"
  [[ -z "${doc_id// }" ]] && continue
  [[ "$doc_id" =~ ^[[:space:]]*# ]] && continue
  withdrawn_row=$((withdrawn_row + 1))

  code="$(curl_code "${BASE_URL}/v1/documents/${doc_id}")"
  status="pass"
  if [[ "$code" != "404" ]]; then
    status="fail"
    failures=$((failures + 1))
  fi
  safe_notes="${notes//|/\\|}"
  echo "| $withdrawn_row | $doc_id | $code | $status | $safe_notes |"
done < "$WITHDRAWN_FILE"

if (( failures > 0 )); then
  echo "" >&2
  echo "Internal beta query pack failed: $failures expectation(s) missed." >&2
  exit 1
fi

echo ""
echo "Internal beta query pack passed."
