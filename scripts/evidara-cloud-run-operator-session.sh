#!/usr/bin/env bash
# One-shot operator session: ensure gcloud login, discover Cloud Run URLs, mint
# ID tokens (impersonation), then run evidara MVP acceptance and/or relevance pack.
#
# Prerequisites:
#   - gcloud, python3, curl, uv (for evidara)
#   - Your user has roles/iam.serviceAccountTokenCreator on the impersonation SA
#   - That SA has roles/run.invoker on platform-control-api and legal-search-api
#
# Optional config (sourced in order if they exist; set shell vars only, no commands):
#   ~/.config/evidara/cloud-run.env
#   ./.evidara-cloud-run.env   (repo root; gitignored — see docs/setup/gcp-local-cloud-run-auth.md)
#
# Usage (repo root):
#   ./scripts/evidara-cloud-run-operator-session.sh dev
#   ./scripts/evidara-cloud-run-operator-session.sh dev --mvp-only
#   ./scripts/evidara-cloud-run-operator-session.sh staging --dry-run
#   ./scripts/evidara-cloud-run-operator-session.sh prod --project evidara-prod --ack-prod
#
# Environment name must be the first argument (after options are not supported — use env first).
#
set -euo pipefail

ROOT="$(cd "$(dirname "$0")/.." && pwd)"
DISCOVER_PY="${ROOT}/scripts/evidara_discover_cloud_run_urls.py"

ENV_NAME="dev"
GCP_PROJECT_ID=""
GCP_REGION="${GCP_REGION:-europe-west6}"
IMPERSONATE_SA="${EVIDARA_GCP_IMPERSONATE_SERVICE_ACCOUNT:-}"
DRY_RUN="false"
MVP_ONLY="false"
REL_ONLY="false"
ACK_PROD="false"
PRINT_EXPORTS="false"
WITH_REL=""

usage() {
  cat <<'EOF'
Usage: scripts/evidara-cloud-run-operator-session.sh <dev|staging|prod> [options]

Ensures gcloud user login, discovers Cloud Run URLs (unless URLs already exported),
mints Bearer tokens via impersonation, then runs:
  - evidara workflow mvp-acceptance --human  (default)
  - scripts/run-staging-relevance-query-pack.sh  (default for staging/dev; skipped for prod unless --with-relevance)

Options:
  --project ID          GCP project (overrides per-env default)
  --region REGION       Cloud Run region (default: europe-west6 or $GCP_REGION)
  --impersonate-sa SA   Service account email (else $EVIDARA_GCP_IMPERSONATE_SERVICE_ACCOUNT or prompt)
  --mvp-only            Only mint + MVP acceptance
  --relevance-only      Only mint + relevance query pack (needs queries file)
  --with-relevance      Include relevance pack (default on dev/staging)
  --no-relevance        Skip relevance pack
  --dry-run             Print discovery + SA; do not mint or call APIs
  --print-exports       After mint, print eval-snippet for tokens (stderr) and exit 0
  --ack-prod            Required with env prod (safety guard)
  -h, --help

Examples:
  ./scripts/evidara-cloud-run-operator-session.sh dev
  EVIDARA_GCP_IMPERSONATE_SERVICE_ACCOUNT='gha-...@project.iam.gserviceaccount.com' \\
    ./scripts/evidara-cloud-run-operator-session.sh dev --no-relevance
EOF
}

if [[ $# -eq 0 ]]; then
  usage >&2
  exit 2
fi
if [[ "${1:-}" == "-h" || "${1:-}" == "--help" ]]; then
  usage
  exit 0
fi

load_optional_config_early() {
  local f
  for f in "${XDG_CONFIG_HOME:-$HOME/.config}/evidara/cloud-run.env" "${ROOT}/.evidara-cloud-run.env"; do
    if [[ -f "$f" ]]; then
      echo "==> Sourcing operator config: $f"
      # shellcheck disable=SC1090
      set -a
      # shellcheck source=/dev/null
      source "$f"
      set +a
    fi
  done
}

load_optional_config_early
IMPERSONATE_SA="${IMPERSONATE_SA:-${EVIDARA_GCP_IMPERSONATE_SERVICE_ACCOUNT:-}}"

while [[ $# -gt 0 ]]; do
  case "$1" in
    dev|staging|prod) ENV_NAME="$1"; shift ;;
    --project) GCP_PROJECT_ID="${2:?}"; shift 2 ;;
    --region) GCP_REGION="${2:?}"; shift 2 ;;
    --impersonate-sa) IMPERSONATE_SA="${2:?}"; shift 2 ;;
    --mvp-only) MVP_ONLY="true"; REL_ONLY="false"; shift ;;
    --relevance-only) REL_ONLY="true"; MVP_ONLY="false"; shift ;;
    --with-relevance) WITH_REL="true"; shift ;;
    --no-relevance) WITH_REL="false"; shift ;;
    --dry-run) DRY_RUN="true"; shift ;;
    --print-exports) PRINT_EXPORTS="true"; shift ;;
    --ack-prod) ACK_PROD="true"; shift ;;
    -h|--help) usage; exit 0 ;;
    *)
      echo "Unknown argument: $1" >&2
      usage >&2
      exit 1
      ;;
  esac
done

if [[ -z "${WITH_REL}" ]]; then
  if [[ "$ENV_NAME" == "prod" ]]; then
    WITH_REL="false"
  else
    WITH_REL="true"
  fi
fi

default_project_for_env() {
  case "$1" in
    dev) echo "project-dacd6b7b-dc96-4534-b82" ;;
    staging) echo "project-dacd6b7b-dc96-4534-b82" ;;
    prod) echo "data-platform-prod-492214" ;;
  esac
}

if [[ -z "${GCP_PROJECT_ID}" ]]; then
  GCP_PROJECT_ID="$(default_project_for_env "$ENV_NAME")"
fi
if [[ "$ENV_NAME" == "prod" && -z "${GCP_PROJECT_ID}" ]]; then
  echo "error: prod requires --project <your-prod-project-id>" >&2
  exit 2
fi
if [[ "$ENV_NAME" == "prod" && "$ACK_PROD" != "true" ]]; then
  echo "error: prod is guarded; pass --ack-prod after confirming project and URLs." >&2
  exit 2
fi

require_cmd() {
  command -v "$1" >/dev/null 2>&1 || {
    echo "error: missing command '$1'" >&2
    exit 1
  }
}

ensure_gcloud_user() {
  require_cmd gcloud
  if gcloud auth list --filter=status:ACTIVE --format='value(account)' 2>/dev/null | grep -q .; then
    echo "==> gcloud: active user account OK"
    return 0
  fi
  echo "==> gcloud: no active user — starting login (browser or URL flow)."
  if [[ -t 1 ]]; then
    gcloud auth login --update-adc
  else
    gcloud auth login --no-launch-browser --update-adc
  fi
}

ensure_impersonation_sa() {
  if [[ -n "${IMPERSONATE_SA}" ]]; then
    export EVIDARA_GCP_IMPERSONATE_SERVICE_ACCOUNT="${IMPERSONATE_SA}"
    echo "==> Impersonation SA: ${EVIDARA_GCP_IMPERSONATE_SERVICE_ACCOUNT}"
    return 0
  fi
  if [[ -n "${EVIDARA_GCP_IMPERSONATE_SERVICE_ACCOUNT:-}" ]]; then
    IMPERSONATE_SA="${EVIDARA_GCP_IMPERSONATE_SERVICE_ACCOUNT}"
    echo "==> Impersonation SA (from env): ${IMPERSONATE_SA}"
    return 0
  fi
  echo "Impersonation service account (needs Token Creator on your user + Run Invoker on PC/LS APIs):" >&2
  echo "  Example: gha-deployer-staging@PROJECT_ID.iam.gserviceaccount.com" >&2
  read -r -p "SA email: " IMPERSONATE_SA
  if [[ -z "${IMPERSONATE_SA}" ]]; then
    echo "error: impersonation SA is required for private Cloud Run." >&2
    exit 2
  fi
  export EVIDARA_GCP_IMPERSONATE_SERVICE_ACCOUNT="${IMPERSONATE_SA}"
}

discover_urls_if_needed() {
  if [[ -n "${EVIDARA_PLATFORM_CONTROL_URL:-}" && -n "${EVIDARA_LEGAL_SEARCH_URL:-}" && -n "${EVIDARA_LEGAL_SEARCH_FRONTEND_URL:-}" && -n "${EVIDARA_PLATFORM_CONTROL_ADMIN_URL:-}" ]]; then
    echo "==> All Cloud Run URLs already set in environment; skipping gcloud discovery."
    export EVIDARA_PLATFORM_CONTROL_URL="${EVIDARA_PLATFORM_CONTROL_URL%/}"
    export EVIDARA_LEGAL_SEARCH_URL="${EVIDARA_LEGAL_SEARCH_URL%/}"
    export EVIDARA_LEGAL_SEARCH_FRONTEND_URL="${EVIDARA_LEGAL_SEARCH_FRONTEND_URL%/}"
    export EVIDARA_PLATFORM_CONTROL_ADMIN_URL="${EVIDARA_PLATFORM_CONTROL_ADMIN_URL%/}"
    return 0
  fi

  if [[ -n "${EVIDARA_PLATFORM_CONTROL_URL:-}" && -n "${EVIDARA_LEGAL_SEARCH_URL:-}" ]]; then
    echo "==> Using pre-set API URLs; filling missing UI URLs via gcloud …"
    export EVIDARA_PLATFORM_CONTROL_URL="${EVIDARA_PLATFORM_CONTROL_URL%/}"
    export EVIDARA_LEGAL_SEARCH_URL="${EVIDARA_LEGAL_SEARCH_URL%/}"
    if [[ -n "${EVIDARA_LEGAL_SEARCH_FRONTEND_URL:-}" && -n "${EVIDARA_PLATFORM_CONTROL_ADMIN_URL:-}" ]]; then
      export EVIDARA_LEGAL_SEARCH_FRONTEND_URL="${EVIDARA_LEGAL_SEARCH_FRONTEND_URL%/}"
      export EVIDARA_PLATFORM_CONTROL_ADMIN_URL="${EVIDARA_PLATFORM_CONTROL_ADMIN_URL%/}"
      return 0
    fi
    local tmp
    tmp="$(mktemp)"
    gcloud run services list --project="${GCP_PROJECT_ID}" --region="${GCP_REGION}" --format=json >"${tmp}"
    # shellcheck disable=SC1090
    eval "$(python3 "${DISCOVER_PY}" <"${tmp}")"
    rm -f "${tmp}"
    return 0
  fi

  echo "==> Discovering Cloud Run URLs (project=${GCP_PROJECT_ID} region=${GCP_REGION}) …"
  local tmp
  tmp="$(mktemp)"
  gcloud run services list --project="${GCP_PROJECT_ID}" --region="${GCP_REGION}" --format=json >"${tmp}"
  # shellcheck disable=SC1090
  eval "$(python3 "${DISCOVER_PY}" <"${tmp}")"
  rm -f "${tmp}"
}

mint_tokens() {
  export EVIDARA_PLATFORM_CONTROL_URL="${EVIDARA_PLATFORM_CONTROL_URL%/}"
  export EVIDARA_LEGAL_SEARCH_URL="${EVIDARA_LEGAL_SEARCH_URL%/}"
  # shellcheck disable=SC1090
  eval "$(
    EVIDARA_GCP_IMPERSONATE_SERVICE_ACCOUNT="${EVIDARA_GCP_IMPERSONATE_SERVICE_ACCOUNT}" \
      EVIDARA_PLATFORM_CONTROL_URL="${EVIDARA_PLATFORM_CONTROL_URL}" \
      EVIDARA_LEGAL_SEARCH_URL="${EVIDARA_LEGAL_SEARCH_URL}" \
      "${ROOT}/scripts/mint-cloud-run-tokens.sh"
  )"
}

preflight_apis() {
  local code
  code="$(
    curl -sS -o /dev/null -w "%{http_code}" \
      -H "Authorization: Bearer ${EVIDARA_PLATFORM_CONTROL_TOKEN}" \
      "${EVIDARA_PLATFORM_CONTROL_URL}/health" || echo "000"
  )"
  if [[ "${code}" != "200" ]]; then
    echo "error: platform-control /health returned HTTP ${code} (expected 200)." >&2
    exit 3
  fi
  code="$(
    curl -sS -o /dev/null -w "%{http_code}" \
      -H "Authorization: Bearer ${EVIDARA_LEGAL_SEARCH_TOKEN}" \
      "${EVIDARA_LEGAL_SEARCH_URL}/v1/search?q=smoke&page_size=1" || echo "000"
  )"
  if [[ "${code}" != "200" ]]; then
    echo "error: legal-search /v1/search returned HTTP ${code} (expected 200)." >&2
    exit 3
  fi
  echo "==> Preflight: platform-control + legal-search token checks OK"
}

run_mvp() {
  echo "==> evidara workflow mvp-acceptance --human"
  (cd "${ROOT}/tools/evidara-cli" && uv run evidara workflow mvp-acceptance --human)
}

run_relevance() {
  echo "==> scripts/run-staging-relevance-query-pack.sh"
  (cd "${ROOT}" && ./scripts/run-staging-relevance-query-pack.sh)
}

# --- main --------------------------------------------------------------------
require_cmd python3
require_cmd curl
require_cmd uv
require_cmd gcloud

export GCP_PROJECT_ID="${GCP_PROJECT_ID}"
gcloud config set project "${GCP_PROJECT_ID}" >/dev/null

ensure_gcloud_user
ensure_impersonation_sa
discover_urls_if_needed

: "${EVIDARA_LEGAL_SEARCH_FRONTEND_URL:=}"
: "${EVIDARA_PLATFORM_CONTROL_ADMIN_URL:=}"
if [[ -z "${EVIDARA_LEGAL_SEARCH_FRONTEND_URL}" || -z "${EVIDARA_PLATFORM_CONTROL_ADMIN_URL}" ]]; then
  echo "error: frontend/admin URLs missing after discovery; set EVIDARA_LEGAL_SEARCH_FRONTEND_URL and EVIDARA_PLATFORM_CONTROL_ADMIN_URL." >&2
  exit 2
fi

export EVIDARA_LEGAL_SEARCH_FRONTEND_URL="${EVIDARA_LEGAL_SEARCH_FRONTEND_URL%/}"
export EVIDARA_PLATFORM_CONTROL_ADMIN_URL="${EVIDARA_PLATFORM_CONTROL_ADMIN_URL%/}"

echo "==> Targets:"
echo "    EVIDARA_PLATFORM_CONTROL_URL=${EVIDARA_PLATFORM_CONTROL_URL}"
echo "    EVIDARA_LEGAL_SEARCH_URL=${EVIDARA_LEGAL_SEARCH_URL}"
echo "    EVIDARA_LEGAL_SEARCH_FRONTEND_URL=${EVIDARA_LEGAL_SEARCH_FRONTEND_URL}"
echo "    EVIDARA_PLATFORM_CONTROL_ADMIN_URL=${EVIDARA_PLATFORM_CONTROL_ADMIN_URL}"

if [[ "$DRY_RUN" == "true" ]]; then
  echo "==> Dry run: stopping before mint."
  exit 0
fi

mint_tokens

if [[ "$PRINT_EXPORTS" == "true" ]]; then
  echo "==> Short-lived tokens (copy into current shell; do not commit):" >&2
  printf 'export EVIDARA_PLATFORM_CONTROL_TOKEN=%q\n' "${EVIDARA_PLATFORM_CONTROL_TOKEN}" >&2
  printf 'export EVIDARA_LEGAL_SEARCH_TOKEN=%q\n' "${EVIDARA_LEGAL_SEARCH_TOKEN}" >&2
  printf 'export E2E_PC_ID_TOKEN=%q\n' "${E2E_PC_ID_TOKEN:-}" >&2
  printf 'export E2E_LS_ID_TOKEN=%q\n' "${E2E_LS_ID_TOKEN:-}" >&2
  exit 0
fi

preflight_apis

if [[ "$REL_ONLY" == "true" ]]; then
  run_relevance
  echo "==> Done (relevance only)."
  exit 0
fi

if [[ "$MVP_ONLY" == "true" ]]; then
  run_mvp
  echo "==> Done (MVP only)."
  exit 0
fi

run_mvp

if [[ "$WITH_REL" == "true" ]]; then
  run_relevance
fi

echo "==> Done."
