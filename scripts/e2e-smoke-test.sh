#!/usr/bin/env bash
set -euo pipefail

# ── E2E Smoke Test ─────────────────────────────────────────────────────
# Exercises the full Evidara pipeline:
#   source → version → approve → run → DI → projection → search
#
# Prerequisites:
#   - gcloud CLI authenticated
#   - jq installed
#   - All services deployed and healthy
#
# Usage:
#   ./scripts/e2e-smoke-test.sh [--env dev]
# ───────────────────────────────────────────────────────────────────────

ENVIRONMENT="dev"
REGION="europe-west6"

while [[ $# -gt 0 ]]; do
  case "$1" in
    --env)
      ENVIRONMENT="${2:?missing value for --env}"
      shift 2
      ;;
    *)
      echo "Unknown argument: $1" >&2
      echo "Usage: $0 [--env dev|staging|prod]" >&2
      exit 1
      ;;
  esac
done

# GCP project — override via env var if needed
PROJECT_ID="${GCP_PROJECT_ID:-data-platform-dev-492214}"

# Auto-auth for private Cloud Run services.
CURL_AUTH_ARGS=()
if command -v gcloud >/dev/null 2>&1; then
  ID_TOKEN="$(gcloud auth print-identity-token 2>/dev/null || true)"
  if [[ -n "${ID_TOKEN}" ]]; then
    CURL_AUTH_ARGS=(-H "Authorization: Bearer ${ID_TOKEN}")
    echo "🔐 Using gcloud identity token for Cloud Run requests."
  fi
fi

# ── Shared curl wrapper: fail on HTTP errors, with sane timeouts ──────
curl_json() {
  local request_url="${!#}"
  local auth_args=("${CURL_AUTH_ARGS[@]}")
  if [[ "${request_url}" =~ ^https?://[^/]+ ]]; then
    if [[ -n "${E2E_PC_ID_TOKEN:-}" && -n "${PC_URL:-}" && "${request_url}" == "${PC_URL}"* ]]; then
      auth_args=(-H "Authorization: Bearer ${E2E_PC_ID_TOKEN}")
    elif [[ -n "${E2E_LS_ID_TOKEN:-}" && -n "${LS_URL:-}" && "${request_url}" == "${LS_URL}"* ]]; then
      auth_args=(-H "Authorization: Bearer ${E2E_LS_ID_TOKEN}")
    fi
  fi
  if [[ ${#auth_args[@]} -eq 0 ]] && command -v gcloud >/dev/null 2>&1; then
    # GitHub OIDC + service-account auth often requires audience-scoped ID tokens.
    if [[ "${request_url}" =~ ^https?://[^/]+ ]]; then
      local audience
      audience="$(echo "${request_url}" | sed -E 's#(https?://[^/]+).*#\1#')"
      local audience_token
      audience_token="$(gcloud auth print-identity-token --audiences="${audience}" 2>/dev/null || true)"
      if [[ -n "${audience_token}" ]]; then
        auth_args=(-H "Authorization: Bearer ${audience_token}")
      fi
    fi
  fi
  curl -fsS --connect-timeout 5 --max-time 30 "${auth_args[@]}" "$@"
}

echo "╔══════════════════════════════════════════════════════════╗"
echo "║        Evidara E2E Smoke Test  (${ENVIRONMENT})                  ║"
echo "╚══════════════════════════════════════════════════════════╝"

# ── Resolve Cloud Run URLs ────────────────────────────────────────────

PC_URL=$(gcloud run services describe "platform-control-api-${ENVIRONMENT}" \
  --project "${PROJECT_ID}" --region "${REGION}" \
  --format='value(status.url)' 2>/dev/null) || {
  echo "❌ Could not resolve platform-control-api URL"; exit 1
}

LS_URL=$(gcloud run services describe "legal-search-api-${ENVIRONMENT}" \
  --project "${PROJECT_ID}" --region "${REGION}" \
  --format='value(status.url)' 2>/dev/null) || {
  echo "❌ Could not resolve legal-search-api URL"; exit 1
}

echo "📡 platform-control-api: ${PC_URL}"
echo "📡 legal-search-api:     ${LS_URL}"
echo ""

# Deterministic acquisition seed URL; can be overridden per environment/run.
SMOKE_SEED_URL="${SMOKE_SEED_URL:-https://example.com}"
SMOKE_REQUEST_TIMEOUT_SECONDS="${SMOKE_REQUEST_TIMEOUT_SECONDS:-10}"

# ── 1. Health checks ─────────────────────────────────────────────────

echo "🔍 Step 1: Health checks..."
for svc in "${PC_URL}" "${LS_URL}"; do
  status=$(curl_json -o /dev/null -w "%{http_code}" "${svc}/health")
  if [ "${status}" != "200" ]; then
    echo "  ❌ ${svc}/health returned ${status}"
    exit 1
  fi
  echo "  ✅ ${svc}/health → 200"
done
echo ""

# ── 2. Seed reference data ──────────────────────────────────────────

echo "🔍 Step 2: Seeding reference data..."
sync_result=$(curl_json -X POST "${PC_URL}/v1/reference-data/hierarchy/sync?dry_run=false")
jur_count=$(echo "${sync_result}" | jq -r '.jurisdictions.created // 0')
echo "  ✅ Hierarchy sync: ${jur_count} jurisdictions created"
echo ""

# ── 3. Create source ────────────────────────────────────────────────

echo "🔍 Step 3: Create source..."
authorities_response=$(curl_json "${PC_URL}/v1/reference-data/authorities")
JURISDICTION_ID=$(echo "${authorities_response}" | jq -r '.data[0].jurisdiction_id // empty')
AUTHORITY_ID=$(echo "${authorities_response}" | jq -r '.data[0].authority_id // empty')
if [[ -z "${JURISDICTION_ID}" || -z "${AUTHORITY_ID}" ]]; then
  echo "  ❌ Could not determine a valid jurisdiction/authority pair"
  echo "  ${authorities_response}" | jq .
  exit 1
fi
echo "  ℹ️  Using jurisdiction=${JURISDICTION_ID}, authority=${AUTHORITY_ID}"

source_body=$(cat <<JSON
{
  "name": "E2E Smoke Test Source $(date +%s)",
  "jurisdiction_id": "${JURISDICTION_ID}",
  "authority_id": "${AUTHORITY_ID}"
}
JSON
)

source_response=$(curl_json -X POST "${PC_URL}/v1/sources" \
  -H "Content-Type: application/json" \
  -d "${source_body}")

SOURCE_ID=$(echo "${source_response}" | jq -r '.source_id')
if [ -z "${SOURCE_ID}" ] || [ "${SOURCE_ID}" = "null" ]; then
  echo "  ❌ Failed to create source: ${source_response}"
  exit 1
fi
echo "  ✅ Source created: ${SOURCE_ID}"
echo ""

# ── 4. Create and approve version ──────────────────────────────────

echo "🔍 Step 4: Create and approve version..."
version_body=$(cat <<JSON
{
  "version_label": "v1-e2e-$(date +%s)",
  "acquisition_spec": {
    "provider": "deterministic_http",
    "seed_url": "${SMOKE_SEED_URL}",
    "request_timeout_seconds": ${SMOKE_REQUEST_TIMEOUT_SECONDS},
    "mode": "crawl",
    "limit": 1,
    "tenant_id": "tenant_public",
    "corpus_id": "corpus_ch_de",
    "scope_type": "global_public",
    "source_origin_kind": "official_primary",
    "trust_tier": "authoritative",
    "language_codes": ["de"],
    "document_type_hint": "decision"
  }
}
JSON
)

version_response=$(curl_json -X POST "${PC_URL}/v1/sources/${SOURCE_ID}/versions" \
  -H "Content-Type: application/json" \
  -d "${version_body}")

VERSION_ID=$(echo "${version_response}" | jq -r '.source_version_id')
if [ -z "${VERSION_ID}" ] || [ "${VERSION_ID}" = "null" ]; then
  echo "  ❌ Failed to create version: ${version_response}"
  exit 1
fi
echo "  ✅ Version created: ${VERSION_ID}"

approve_response=$(curl_json -X POST "${PC_URL}/v1/versions/${VERSION_ID}/approve")
approve_status=$(echo "${approve_response}" | jq -r '.status')
echo "  ✅ Version approved: status=${approve_status}"
echo ""

# ── 5. Trigger run ──────────────────────────────────────────────────

echo "🔍 Step 5: Trigger acquisition run..."
run_response=$(curl_json -X POST "${PC_URL}/v1/runs" \
  -H "Content-Type: application/json" \
  -d "{\"source_id\": \"${SOURCE_ID}\", \"source_version_id\": \"${VERSION_ID}\"}")

RUN_ID=$(echo "${run_response}" | jq -r '.run_id')
if [ -z "${RUN_ID}" ] || [ "${RUN_ID}" = "null" ]; then
  echo "  ❌ Failed to create run: ${run_response}"
  exit 1
fi
echo "  ✅ Run triggered: ${RUN_ID}"
echo ""

# ── 6. Poll for completion ──────────────────────────────────────────

echo "🔍 Step 6: Polling for run completion..."
MAX_POLLS=30
POLL_INTERVAL=10
for i in $(seq 1 ${MAX_POLLS}); do
  run_status_response=$(curl_json "${PC_URL}/v1/runs/${RUN_ID}")
  run_status=$(echo "${run_status_response}" | jq -r '.status')
  echo "  [${i}/${MAX_POLLS}] Run status: ${run_status}"

  if [ "${run_status}" = "completed" ]; then
    echo "  ✅ Run completed!"
    break
  elif [ "${run_status}" = "failed" ] || [ "${run_status}" = "cancelled" ]; then
    echo "  ❌ Run ${run_status}!"
    echo "  ${run_status_response}" | jq .
    exit 1
  fi

  if [ "${i}" -eq "${MAX_POLLS}" ]; then
    echo "  ❌ Timeout after $((MAX_POLLS * POLL_INTERVAL))s — run did not complete."
    echo "  Check logs: gcloud logging read 'resource.type=cloud_run_revision' --project=${PROJECT_ID} --limit=20"
    exit 1
  fi

  sleep ${POLL_INTERVAL}
done
echo ""

# ── 7. Wait for DI signals ─────────────────────────────────────────

echo "🔍 Step 7: Verifying DI processing signals..."
MAX_DI_POLLS=12
DI_INTERVAL=5
for i in $(seq 1 ${MAX_DI_POLLS}); do
  status_response=$(curl_json "${PC_URL}/v1/runs/${RUN_ID}/processing-status")
  lifecycle_response=$(curl_json "${PC_URL}/v1/runs/${RUN_ID}/document-lifecycle")

  status_count=$(echo "${status_response}" | jq -r '.data | length')
  canonical_ready_count=$(echo "${status_response}" | jq -r '[.data[] | select(.status=="canonical_ready")] | length')
  processed_count=$(echo "${lifecycle_response}" | jq -r '[.data[] | select(.event_type=="document.processed")] | length')
  echo "  [${i}/${MAX_DI_POLLS}] statuses=${status_count}, canonical_ready=${canonical_ready_count}, processed=${processed_count}"

  if [ "${canonical_ready_count}" -gt 0 ] && [ "${processed_count}" -gt 0 ]; then
    echo "  ✅ DI signals observed"
    break
  fi

  if [ "${i}" -eq "${MAX_DI_POLLS}" ]; then
    echo "  ❌ Timed out waiting for DI canonical_ready and document.processed signals"
    exit 1
  fi

  sleep ${DI_INTERVAL}
done
echo ""

# ── 8. Check projection history ────────────────────────────────────

echo "🔍 Step 8: Checking projection history..."
projection_history=$(curl_json --get \
  --data-urlencode "run_id=${RUN_ID}" \
  --data-urlencode "limit=50" \
  --data-urlencode "offset=0" \
  "${LS_URL}/v1/projections/events/history")
run_total_events=$(echo "${projection_history}" | jq -r '.total // 0')
applied=$(echo "${projection_history}" | jq -r '[.data[] | select(.status=="applied")] | length')
RUN_DOCUMENT_ID=$(echo "${projection_history}" | jq -r '([.data[] | select(.status=="applied")][0].documentId // empty)')
echo "  📊 Projection stats (run-scoped): total=${run_total_events}, applied=${applied}"

if [ "${applied}" -gt 0 ] && [[ -n "${RUN_DOCUMENT_ID}" ]]; then
  echo "  ✅ Projections applied for run ${RUN_ID} (document_id=${RUN_DOCUMENT_ID})"
else
  echo "  ❌ No run-scoped projections applied for run ${RUN_ID}."
  echo "  ${projection_history}" | jq .
  exit 1
fi
echo ""

# ── 9. Search for indexed document ──────────────────────────────────

echo "🔍 Step 9: Searching for indexed documents..."
MAX_SEARCH_PAGES=10
SEARCH_PAGE_SIZE=100
found_document=0
matched_title=""
result_count=0

for page in $(seq 1 ${MAX_SEARCH_PAGES}); do
  search_response=$(curl_json --get \
    --data-urlencode "q=*" \
    --data-urlencode "page=${page}" \
    --data-urlencode "page_size=${SEARCH_PAGE_SIZE}" \
    "${LS_URL}/v1/search")
  result_count=$(echo "${search_response}" | jq -r '.results | length')
  matching_result_count=$(echo "${search_response}" | jq -r --arg doc "${RUN_DOCUMENT_ID}" '[.results[] | select(.id == $doc)] | length')
  echo "  [${page}/${MAX_SEARCH_PAGES}] Search results: ${result_count} (matching run document=${matching_result_count})"

  if [ "${matching_result_count}" -gt 0 ]; then
    found_document=1
    matched_title=$(echo "${search_response}" | jq -r --arg doc "${RUN_DOCUMENT_ID}" '.results[] | select(.id == $doc) | .title' | head -n 1)
    break
  fi

  if [ "${result_count}" -lt "${SEARCH_PAGE_SIZE}" ]; then
    break
  fi
done

if [ "${found_document}" -eq 1 ]; then
  echo "  ✅ Found run-scoped indexed document: ${matched_title}"
else
  echo "  ❌ Run-scoped search failed for document ${RUN_DOCUMENT_ID}."
  echo "  Last search page payload:"
  echo "  ${search_response}" | jq .
  exit 1
fi
echo ""

# ── Summary ─────────────────────────────────────────────────────────

echo "╔══════════════════════════════════════════════════════════╗"
echo "║                   E2E Smoke Test ✅ PASSED               ║"
echo "╠══════════════════════════════════════════════════════════╣"
echo "║  Source:     ${SOURCE_ID}  "
echo "║  Version:    ${VERSION_ID}  "
echo "║  Run:        ${RUN_ID}  "
echo "║  Projections applied: ${applied}  "
echo "║  Search results:      ${result_count}  "
echo "╚══════════════════════════════════════════════════════════╝"
