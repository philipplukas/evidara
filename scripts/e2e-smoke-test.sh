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

# ── Shared curl wrapper: fail on HTTP errors, with sane timeouts ──────
curl_json() {
  curl -fsS --connect-timeout 5 --max-time 30 "$@"
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
source_body=$(cat <<'JSON'
{
  "name": "E2E Smoke Test Source",
  "jurisdiction_id": "jur_ch",
  "authority_id": "auth_bger"
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
    "seed_url": "https://www.bger.ch/ext/eurospider/live/de/php/aza/http/index.php?lang=de&type=show_document&highlight_docid=aza://06-11-2024-4A_400-2024",
    "mode": "scrape",
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

# ── 7. Check projection history ────────────────────────────────────

echo "🔍 Step 7: Checking projection history..."
projection_stats=$(curl_json "${LS_URL}/v1/projections/events/history/stats")
total_events=$(echo "${projection_stats}" | jq -r '.totalEvents // 0')
applied=$(echo "${projection_stats}" | jq -r '.applied // 0')
echo "  📊 Projection stats: total=${total_events}, applied=${applied}"

if [ "${applied}" -gt 0 ]; then
  echo "  ✅ Projections applied successfully!"
else
  echo "  ❌ No projections applied — push subscription may not be wired."
  exit 1
fi
echo ""

# ── 8. Search for indexed document ──────────────────────────────────

echo "🔍 Step 8: Searching for indexed documents..."
search_response=$(curl_json "${LS_URL}/v1/search?q=Verantwortlichkeit")
result_count=$(echo "${search_response}" | jq -r '.results | length')
echo "  📊 Search results: ${result_count}"

if [ "${result_count}" -gt 0 ]; then
  first_title=$(echo "${search_response}" | jq -r '.results[0].title')
  echo "  ✅ Found indexed document: ${first_title}"
else
  echo "  ❌ No search results — documents may not have been indexed correctly."
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
